from __future__ import print_function
import time
import logging
import h5py
import epics

import filestore.api as fs_api
import uuid

from ophyd.controls.areadetector.detectors import (AreaDetector, ADSignal)
from ophyd.controls.area_detector import AreaDetectorFileStore
from ophyd.controls.detector import DetectorStatus

from .utils import (makedirs, get_total_scan_points)

from ..handlers import Xspress3HDF5Handler
from ..handlers.xspress3 import XRF_DATA_KEY

logger = logging.getLogger(__name__)


class Xspress3FileStore(AreaDetectorFileStore):
    def __init__(self, det, basename, file_template='%s%s_%6.6d.h5',
                 **kwargs):
        super().__init__(basename, cam='', reset_acquire=False,
                         use_image_mode=False, **kwargs)

        self._det = det
        # Use the EpicsSignal file_template from the detector
        self._file_template = det.hdf5.file_template
        # (_file_template is used in _make_filename, etc)
        self.file_template = file_template
        self._filestore_res = None

    def _insert_data(self, detvals, timestamp, seq_num):
        for chan in range(1, 9):
            mds_key = '{}_ch{}'.format(self._det.name, chan)

            datum_uid = str(uuid.uuid4())
            datum_key = 'ch%d_spectrum_%.5d-%s' % (chan, seq_num, datum_uid)
            datum_args = {'frame': seq_num, 'channel': chan}
            fs_api.insert_datum(self._filestore_res, datum_key, datum_args)
            detvals[mds_key] = {'timestamp': timestamp,
                                'value': datum_key,
                                }

    def read(self):
        detvals = {}

        self._insert_data(detvals, time.time(), self._abs_trigger_count)
        self._abs_trigger_count += 1
        return detvals

    def bulk_read(self, count):
        ret = {}

        def insert_datum(**datum_args):
            datum_uid = str(uuid.uuid4())
            fs_api.insert_datum(self._filestore_res, datum_uid, datum_args)
            return datum_uid

        for chan in range(1, 9):
            mds_key = '{}_ch{}'.format(self._det.name, chan)
            ret[mds_key] = [insert_datum(frame=seq_num, channel=chan)
                            for seq_num in range(count)]

        return ret

    def _make_filename(self, **kwargs):
        super()._make_filename(**kwargs)

        makedirs(self._store_file_path)

        # TODO NumCapture=1e6 causes 25GB (!) HDF files and insane slowdowns.
        #      why is this set this way?
        # self._write_plugin('NumCapture', 1000, self._file_plugin)
        # OK, removing ROIs from hdf5 file as they're redundant information
        # this also makes it such that ~500 1-million entry attributes
        # are inserted per scan

    def deconfigure(self, *args, **kwargs):
        # self._det.hdf5.capture.put(0)
        try:
            while self._det.hdf5.capture.value == 1:
                logger.warning('Still capturing data .... waiting.')
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.warning('Still capturing data .... interrupted.')

        self._det.trigger_mode.put('Internal')
        self.set_scan(None)

        # TODO
        self._old_image_mode = self._image_mode.value
        self._old_acquire = self._acquire.value

        super().deconfigure(*args, **kwargs)

    def configure(self, *args, **kwargs):
        print('configure')
        num_points = get_total_scan_points(self._num_scan_points)

        logger.debug('Stopping xspress3 acquisition')
        self._det.acquire.put(0)

        logger.debug('Erasing old spectra')
        self._det.xs_erase.put(1)
        time.sleep(0.1)

        logger.debug('Setting up triggering')
        self._det.trigger_mode.put('TTL Veto Only')
        self._det.num_images.put(num_points)
        # self._det.trigger_mode.put('Internal')

        logger.debug('Configuring other filestore stuff')
        super(Xspress3FileStore, self).configure(*args, **kwargs)

        logger.debug('Making the filename')
        self._make_filename(seq=0)

        logger.debug('Setting up hdf5 plugin: ioc path: %s filename: %s',
                     self._ioc_file_path, self._filename)
        self._det.hdf5.file_template.put(self.file_template, wait=True)
        self._det.hdf5.file_number.put(0)
        self._det.hdf5.enable.put(1)
        self._det.hdf5.file_path.put(self._ioc_file_path, wait=True)
        self._det.hdf5.file_name.put(self._filename, wait=True)

        if not self._det.hdf5.file_path_exists.value:
            raise IOError("Path {} does not exits on IOC!! Please Check"
                          .format(self._det.hdf5.file_path.value))

        logger.debug('Inserting the filestore resource')
        self._filestore_res = self._insert_fs_resource()

        logger.debug('Starting acquisition')
        self._det.acquire.put(1, wait=False)
        self._det.hdf5.capture.put(1, wait=False)

    def acquire(self, **kwargs):
        status = DetectorStatus(self)
        status._finished()
        # scaler/zebra take care of timing
        return status

    def describe(self):
        # TODO: describe is called prior to configure, so the filestore resource
        #       is not yet generated
        size = (self._det.hdf5.width.value, )

        spec_desc = {'external': 'FILESTORE:',
                     'dtype': 'array',
                     'shape': size,
                     }

        if self._filestore_res is not None:
            source = 'FileStore:{0.id!s}'.format(self._filestore_res)
        else:
            source = 'FileStore:'

        spec_desc['source'] = source

        desc = {}
        for chan in range(1, 9):
            desc['{}_ch{}'.format(self._det.name, chan)] = spec_desc

        return desc

    def _insert_fs_resource(self):
        return fs_api.insert_resource(Xspress3HDF5Handler.HANDLER_NAME,
                                      self.store_filename, {})

    @property
    def store_filename(self):
        return self._store_filename

    @property
    def ioc_filename(self):
        return self._ioc_filename

    def set_scan(self, scan):
        self._scan = scan

        if scan is None:
            return

        self._num_scan_points = scan.npts + 1


class Xspress3Detector(AreaDetector):
    _html_docs = ['']
    xs_config_path = ADSignal('CONFIG_PATH', has_rbv=True)
    xs_config_save_path = ADSignal('CONFIG_SAVE_PATH', has_rbv=True)
    xs_connect = ADSignal('CONNECT')
    xs_connected = ADSignal('CONNECTED')
    xs_ctrl_dtc = ADSignal('CTRL_DTC', has_rbv=True)
    xs_ctrl_mca_roi = ADSignal('CTRL_MCA_ROI', has_rbv=True)
    xs_debounce = ADSignal('DEBOUNCE', has_rbv=True)
    xs_disconnect = ADSignal('DISCONNECT')
    xs_erase = ADSignal('ERASE')
    xs_erase_array_counters = ADSignal('ERASE_ArrayCounters')
    xs_erase_attr_reset = ADSignal('ERASE_AttrReset')
    xs_erase_proc_reset_filter = ADSignal('ERASE_PROC_ResetFilter')
    xs_frame_count = ADSignal('FRAME_COUNT_RBV', rw=False)
    xs_hdf_capture = ADSignal('HDF5:Capture_RBV', rw=False)
    xs_hdf_num_capture_calc = ADSignal('HDF5:NumCapture_CALC')
    xs_invert_f0 = ADSignal('INVERT_F0', has_rbv=True)
    xs_invert_veto = ADSignal('INVERT_VETO', has_rbv=True)
    xs_max_frames = ADSignal('MAX_FRAMES_RBV', rw=False)
    xs_max_frames_driver = ADSignal('MAX_FRAMES_DRIVER_RBV', rw=False)
    xs_max_num_channels = ADSignal('MAX_NUM_CHANNELS_RBV', rw=False)
    xs_max_spectra = ADSignal('MAX_SPECTRA', has_rbv=True)
    xs_name = ADSignal('NAME')
    xs_num_cards = ADSignal('NUM_CARDS_RBV', rw=False)
    xs_num_channels = ADSignal('NUM_CHANNELS', has_rbv=True)
    xs_num_frames_config = ADSignal('NUM_FRAMES_CONFIG', has_rbv=True)
    xs_reset = ADSignal('RESET')
    xs_restore_settings = ADSignal('RESTORE_SETTINGS')
    xs_run_flags = ADSignal('RUN_FLAGS', has_rbv=True)
    xs_save_settings = ADSignal('SAVE_SETTINGS')
    xs_trigger = ADSignal('TRIGGER')
    xs_update = ADSignal('UPDATE')
    xs_update_attr = ADSignal('UPDATE_AttrUpdate')

    def __init__(self, prefix, file_path='', ioc_file_path='',
                 default_channels=None, num_roi=16, channel_prefix='Det',
                 **kwargs):
        AreaDetector.__init__(self, prefix, **kwargs)

        self.filestore = Xspress3FileStore(self, self._base_prefix,
                                           stats=[], shutter=None,
                                           file_path=file_path,
                                           ioc_file_path=ioc_file_path,
                                           name=self.name)

        if default_channels is None:
            default_channels = [1, 2, 3]

        self.default_channels = list(default_channels)
        self.num_roi = int(num_roi)
        self._roi_config = {}
        self._channel_prefix = channel_prefix

    def get_hdf5_rois(self, fn, rois=None, wait=True,
                      data_key=XRF_DATA_KEY):
        if rois is None:
            rois = [roi for nchan, chan in sorted(self._roi_config.items())
                    for nroi, roi in sorted(chan.items())
                    ]

        warned = False
        num_points = self.num_images.value
        while True:
            try:
                try:
                    hdf = h5py.File(fn, 'r')
                except IOError:
                    if not warned:
                        logger.error('Xspress3 hdf5 file still open; press '
                                     'Ctrl-C to cancel')
                        warned = True

                    time.sleep(0.2)
                    self.hdf5.capture.put(0)
                    self.acquire.put(0)
                    if not wait:
                        raise RuntimeError('Unable to open HDF5 file; retry '
                                           'disabled')

                else:
                    if warned:
                        logger.info('Xspress3 hdf5 file opened')
                    break
            except KeyboardInterrupt:
                raise RuntimeError('Unable to open HDF5 file; interrupted '
                                   'by Ctrl-C')

        handler = Xspress3HDF5Handler(hdf, key=data_key)
        for roi_info in sorted(rois, key=lambda x: x.name):
            roi = handler.get_roi(roi_info, max_points=num_points)
            yield Xspress3ROI(chan=roi_info.chan, ev_low=roi_info.ev_low,
                              ev_high=roi_info.ev_high, name=roi_info.name,
                              data=roi)

    def _roi_pvs(self, channel, roi):
        pvs = ['C{channel}_MCA_ROI{roi}_LLM',
               'C{channel}_MCA_ROI{roi}_HLM',
               'C{channel}_ROI{roi}:EnableCallbacks',
               ]

        prefix = self._base_prefix
        return [''.join((prefix, pv.format(channel=channel, roi=roi)))
                for pv in pvs]

    def _get_epics_roi_config(self, channel, roi):
        pvs = self._roi_pvs(channel, roi)
        return [epics.caget(pv) for pv in pvs]

    def _get_roi_name(self, channel, roi, suffix):
        if self._channel_prefix is not None:
            return '{}{}_{}'.format(self._channel_prefix, channel, suffix)
        else:
            return suffix

    def set_roi_config(self, channel, roi, ev_low, ev_high, name=None):
        bin_low = int(ev_low / 10)
        bin_high = int(ev_high / 10)

        if channel not in self._roi_config:
            self._roi_config[channel] = {}

        if ev_low == ev_high == 0:
            enable = 0
            try:
                del self._roi_config[channel][roi]
            except KeyError:
                pass
        else:
            enable = 1
            info = Xspress3ROI(chan=channel, ev_low=ev_low, ev_high=ev_high,
                               name=name)
            self._roi_config[channel][roi] = info

            if roi > self.num_roi:
                logger.warning('ROI {} will be recorded in fly scans but will '
                               'not be available for live preview (num_roi={})'
                               ''.format(name, self.num_roi))

        if roi <= self.num_roi:
            low_pv, high_pv, enable_pv = self._roi_pvs(channel, roi)
            return [epics.caput(pv, value) for pv, value
                    in zip((high_pv, low_pv, enable_pv),
                           (bin_high, bin_low, enable))]

    def clear_roi_config(self, channel, roi):
        return self.set_roi_config(channel, roi, 0, 0)

    def clear_all_rois(self, rois=None, channels=None):
        if channels is None:
            channels = self.default_channels

        if rois is None:
            rois = range(1, self.num_roi + 1)

        for channel in channels:
            for roi in rois:
                values = self._get_epics_roi_config(channel, roi)
                ev_low, ev_high, enabled = values
                if (ev_low == ev_high == 0) or not enabled:
                    pass
                else:
                    self.clear_roi_config(channel, roi)

    def add_roi(self, ev_low, ev_high, name, channels=None):
        if channels is None:
            channels = self.default_channels

        for channel in channels:
            try:
                roi = max(self._roi_config[channel]) + 1
            except ValueError:
                roi = 1

            self.set_roi_config(channel, roi, ev_low, ev_high,
                                name=self._get_roi_name(channel, roi, name))

    @property
    def filestore_id(self):
        return self.filestore._filestore_res


class Xspress3ROI(object):
    def __init__(self, chan=1, ev_low=1, ev_high=1000, data=None,
                 name=None):
        self._chan = chan
        self._ev_low = ev_low
        self._ev_high = ev_high
        self._bin_low = self._ev_to_bin(ev_low)
        self._bin_high = self._ev_to_bin(ev_high)
        self._data = data
        self._name = name

    @property
    def name(self):
        return self._name

    @property
    def data(self):
        return self._data

    @property
    def chan(self):
        return self._chan

    @property
    def ev_low(self):
        return self._ev_low

    @property
    def ev_high(self):
        return self._ev_high

    @property
    def bin_low(self):
        return self._bin_low

    @property
    def bin_high(self):
        return self._bin_high

    def _ev_to_bin(self, ev):
        return int(ev / 10) - int((ev / 10) % 10)

    def __repr__(self):
        return '{0.__class__.__name__}(chan={0.chan}, ev_low={0.ev_low}, ' \
               'ev_high={0.ev_high}, name={0.name!r}, '\
               'data={0.data!r})'.format(self)
