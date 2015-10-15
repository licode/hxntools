from __future__ import print_function
import time
import logging
import uuid
import itertools

from collections import namedtuple

import h5py
import filestore.api as fs_api
from filestore.commands import bulk_insert_datum

from ophyd.controls.areadetector.detectors import (AreaDetector, ADBase,
                                                   ADSignal)
from ophyd.controls.area_detector import AreaDetectorFileStore
from ophyd.controls.detector import (DetectorStatus, Detector)

from .utils import makedirs

from ..handlers import Xspress3HDF5Handler
from ..handlers.xspress3 import XRF_DATA_KEY

logger = logging.getLogger(__name__)


class Xspress3FileStore(AreaDetectorFileStore):
    '''Xspress3 acquisition -> filestore'''

    def __init__(self, det, basename, file_template='%s%s_%6.6d.h5',
                 config_time=0.5,
                 mds_key_format='{self._det.name}_ch{chan}',
                 **kwargs):
        super().__init__(basename, cam='', reset_acquire=False,
                         use_image_mode=False, **kwargs)

        self._det = det
        # Use the EpicsSignal file_template from the detector
        self._file_template = det.hdf5.file_template
        # (_file_template is used in _make_filename, etc)
        self.file_template = file_template
        self._filestore_res = None
        self.channels = list(range(1, det.num_channels + 1))
        self._total_points = None
        self._master = None
        self._external_trig = None
        self._config_time = config_time
        self.mds_keys = {chan: mds_key_format.format(self=self, chan=chan)
                         for chan in self.channels}
        self._file_plugin = None

    def _get_datum_args(self, seq_num):
        for chan in self.channels:
            yield {'frame': seq_num, 'channel': chan}

    def read(self):
        timestamp = time.time()
        uids = [str(uuid.uuid4()) for ch in self.channels]

        bulk_insert_datum(self._filestore_res, uids,
                          self._get_datum_args(self._abs_trigger_count))

        self._abs_trigger_count += 1
        return {self.mds_keys[ch]: {'timestamp': timestamp,
                                    'value': uid,
                                    }
                for uid, ch in zip(uids, self.channels)
                }

    def bulk_read(self, timestamps):
        channels = self.channels
        ch_uids = {ch: [str(uuid.uuid4()) for ts in timestamps]
                   for ch in channels}

        count = len(timestamps)

        def get_datum_args():
            for ch in channels:
                for seq_num in range(count):
                    yield {'frame': seq_num,
                           'channel': ch}

        uids = [ch_uids[ch] for ch in channels]
        bulk_insert_datum(self._filestore_res, itertools.chain(*uids),
                          get_datum_args())

        return {self.mds_keys[ch]: ch_uids[ch]
                for ch in channels
                }

    def _make_filename(self, **kwargs):
        super()._make_filename(**kwargs)

        makedirs(self._store_file_path)

    def deconfigure(self, *args, **kwargs):
        # self._det.hdf5.capture.put(0)
        try:
            i = 0
            while self._det.hdf5.capture.value == 1:
                i += 1
                if (i % 50) == 0:
                    logger.warning('Still capturing data .... waiting.')
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.warning('Still capturing data .... interrupted.')

        self._det.trigger_mode.put('Internal')
        self._total_points = None

        # TODO
        self._old_image_mode = self._image_mode.value
        self._old_acquire = self._acquire.value

        super().deconfigure(*args, **kwargs)

    def set(self, total_points=0, master=None, external_trig=False,
            **kwargs):
        self._total_points = total_points
        self._master = master
        self._external_trig = external_trig

    def configure(self, state=None):
        ext_trig = (self._master is not None or self._external_trig)

        logger.debug('Stopping xspress3 acquisition')
        self._det.acquire.put(0)

        time.sleep(0.1)

        if ext_trig:
            logger.debug('Setting up external triggering')
            self._det.trigger_mode.put('TTL Veto Only')
            self._det.num_images.put(self._total_points)
        else:
            logger.debug('Setting up internal triggering')
            self._det.trigger_mode.put('Internal')
            self._det.num_images.put(1)

        logger.debug('Configuring other filestore stuff')
        super(Xspress3FileStore, self).configure(*args, **kwargs)

        logger.debug('Making the filename')
        self._make_filename(seq=0)

        logger.debug('Setting up hdf5 plugin: ioc path: %s filename: %s',
                     self._ioc_file_path, self._filename)
        self._det.hdf5.file_template.put(self.file_template, wait=True)
        self._det.hdf5.file_number.put(0)
        self._det.hdf5.blocking_callbacks.put(1)
        self._det.hdf5.enable.put(1)
        self._det.hdf5.file_path.put(self._ioc_file_path, wait=True)
        self._det.hdf5.file_name.put(self._filename, wait=True)

        if not self._det.hdf5.file_path_exists.value:
            raise IOError("Path {} does not exits on IOC!! Please Check"
                          .format(self._det.hdf5.file_path.value))

        logger.debug('Inserting the filestore resource')
        self._filestore_res = self._insert_fs_resource()

        logger.debug('Erasing old spectra')
        self._det.xs_erase.put(1)
        self._det.hdf5.capture.put(1, wait=False)

        if ext_trig:
            logger.debug('Starting acquisition (waiting for triggers)')
            self._det.acquire.put(1, wait=False)

        # Xspress3 needs a bit of time to configure itself...
        time.sleep(self._config_time)

    @property
    def count_time(self):
        return self._det.acquire_period.value

    @count_time.setter
    def count_time(self, val):
        self._det.acquire_period.put(val)

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
        for chan in self.channels:
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


class Xspress3Detector(AreaDetector):
    '''Quantum Detectors Xspress3 detector'''

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
                 default_channels=None, num_roi=16, num_channels=8,
                 channel_prefix=None, roi_sums=False,
                 **kwargs):
        AreaDetector.__init__(self, prefix, **kwargs)

        if default_channels is None:
            default_channels = [1, 2, 3]

        self.default_channels = list(default_channels)
        self.num_roi = int(num_roi)
        self.num_channels = int(num_channels)
        self.rois = Xspress3Rois(self, channel_prefix=channel_prefix,
                                 use_sums=roi_sums)

        self.filestore = Xspress3FileStore(self, self._base_prefix,
                                           stats=[], shutter=None,
                                           file_path=file_path,
                                           ioc_file_path=ioc_file_path,
                                           name=self.name)

    @property
    def filestore_id(self):
        return self.filestore._filestore_res

    @property
    def prefix(self):
        return self._prefix


def ev_to_bin(ev):
    '''Convert eV to bin number'''
    return int(ev / 10)


def bin_to_ev(bin_):
    '''Convert bin number to eV'''
    return int(bin_) * 10


_roi_tuple = namedtuple('ROISnapshot', 'name chan ev_low ev_high bin_low '
                                       'bin_high data epics_roi')


class ROISnapshot(_roi_tuple):
    '''A non-configurable snapshot of an Xspress3 ROI'''

    def __new__(cls, chan=1, ev_low=None, ev_high=None,
                bin_low=None, bin_high=None, name='name', data=None,
                epics_roi=None):
        if ev_low is not None and ev_high is not None:
            bin_low = ev_to_bin(ev_low)
            bin_high = ev_to_bin(ev_high)
        elif bin_low is not None and bin_high is not None:
            ev_low = bin_to_ev(bin_low)
            ev_high = bin_to_ev(bin_high)
        else:
            raise ValueError('Bin or energy must be specified')

        return super(ROISnapshot, cls).__new__(cls, name, chan, ev_low,
                                               ev_high, bin_low, bin_high,
                                               data, epics_roi)


class EpicsROI(ADBase, Detector):
    '''A configurable Xspress3 EPICS ROI'''

    array = ADSignal('C{self.channel}_ROI{self.roi_num}:ArrayData_RBV',
                     rw=False)
    value = ADSignal('C{self.channel}_ROI{self.roi_num}:Value_RBV', rw=False)
    value_sum = ADSignal('C{self.channel}_ROI{self.roi_num}:ValueSum_RBV',
                         rw=False)
    bin_low = ADSignal('C{self.channel}_MCA_ROI{self.roi_num}_LLM')
    bin_high = ADSignal('C{self.channel}_MCA_ROI{self.roi_num}_HLM')
    enabled = ADSignal('C{self.channel}_ROI{self.roi_num}:EnableCallbacks',
                       has_rbv=True)
    vis_enabled = ADSignal('C{self.channel}_PluginControlVal', rw=True)

    def __init__(self, prefix, channel, roi_num, use_sum=False, **kwargs):
        super(EpicsROI, self).__init__(prefix, **kwargs)
        self._channel = channel
        self._roi_num = roi_num
        self._use_sum = use_sum

    @property
    def channel(self):
        return self._channel

    @property
    def roi_num(self):
        return self._roi_num

    @property
    def prefix(self):
        return self._prefix

    @property
    def ev_low(self):
        return bin_to_ev(self.bin_low.value)

    @ev_low.setter
    def ev_low(self, ev):
        self.bin_low.value = ev_to_bin(ev)

    @property
    def ev_high(self):
        return bin_to_ev(self.bin_high.value)

    @ev_high.setter
    def ev_high(self, ev):
        self.bin_high.value = ev_to_bin(ev)

    def clear(self):
        if self.bin_low.value == self.bin_high.value == 0:
            return

        self.bin_low.put(0)
        self.bin_high.put(0)
        self.enabled.put(0)

    def set_roi(self, low, high, units='ev'):
        if units == 'ev':
            low = ev_to_bin(low)
            high = ev_to_bin(high)
        elif units == 'bin':
            low = int(low)
            high = int(high)
        else:
            raise ValueError('Unknown units. Expected either "ev" or "bin"')

        enable = 1 if high > low else 0
        changed = any([self.bin_high.value != high,
                       self.bin_low.value != low,
                       self.enabled.value != enable])

        if changed:
            logger.debug('Setting up EPICS ROI: name=%s bins=(%s, %s) '
                         'enable=%s prefix=%s channel=%s',
                         self.name, low, high, enable, self._prefix,
                         self._channel)
            if high <= self.bin_low.value:
                self.bin_low.put(0)

            self.bin_high.put(high)
            self.bin_low.put(low)
            self.enabled.put(enable)

    @property
    def _read_signal(self):
        '''The signal which is read for data acquisition'''
        if self._use_sum:
            return self.value_sum
        return self.value

    def read(self):
        return {self.name: dict(value=self._read_signal.get(),
                                timestamp=time.time())}

    def describe(self):
        source = 'PV:{}'.format(self._read_signal.pvname)
        return {self.name: dict(dtype='number', shape=[],
                                source=source)}


class Xspress3Rois(object):
    '''Xspress3 ROI configuration

    .. note:: Can optionally configure more than the EPICS IOC supports
    '''
    def __init__(self, det, channel_prefix=None, limit_rois=False,
                 name_format='{self.channel_prefix}{channel}_{name}',
                 use_sums=False):
        self._det = det
        self._roi_config = {}
        self.channel_prefix = channel_prefix
        self.name_format = name_format
        self.num_roi = det.num_roi
        self.num_channels = det.num_channels
        self.limit_rois = limit_rois
        self.use_sums = use_sums

    def read_hdf5(self, fn, rois=None, wait=True, max_retries=2,
                  data_key=XRF_DATA_KEY):
        '''Read ROIs from an hdf5 file'''

        if rois is None:
            rois = [roi for nchan, chan in sorted(self._roi_config.items())
                    for nroi, roi in sorted(chan.items())
                    ]

        warned = False
        det = self._det
        num_points = det.num_images.value
        retry = 0
        while retry < max_retries:
            retry += 1
            try:
                try:
                    hdf = h5py.File(fn, 'r')
                except (IOError, OSError):
                    if not warned:
                        logger.error('Xspress3 hdf5 file still open; press '
                                     'Ctrl-C to cancel')
                        warned = True

                    time.sleep(2.0)
                    det.hdf5.capture.put(0)
                    det.acquire.put(0)
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

        if retry >= max_retries:
            raise RuntimeError('Unable to open HDF5 file; exceeded maximum '
                               'retries')
        else:
            handler = Xspress3HDF5Handler(hdf, key=data_key)
            for roi_info in sorted(rois, key=lambda x: x.name):
                roi_data = handler.get_roi(roi_info, max_points=num_points)
                yield ROISnapshot(chan=roi_info.chan, ev_low=roi_info.ev_low,
                                  ev_high=roi_info.ev_high, name=roi_info.name,
                                  data=roi_data)

    def get_roi_name(self, channel, suffix):
        '''Format an ROI name according to the channel prefix'''
        if self.name_format is not None:
            return self.name_format.format(self=self, channel=channel,
                                           name=suffix)
        else:
            return suffix

    def set(self, channel, roi, ev_low, ev_high, name=None):
        '''Configure an ROI on a specific channel'''
        if channel not in self._roi_config:
            self._roi_config[channel] = {}

        epics_roi = None

        ev_low = int(ev_low)
        ev_high = int(ev_high)

        if ev_low == ev_high == 0:
            try:
                epics_roi = self._roi_config[channel][roi].epics_roi
                del self._roi_config[channel][roi]
            except KeyError:
                return

            if epics_roi is not None:
                epics_roi.clear()
        else:
            if roi <= self.num_roi:
                epics_roi = EpicsROI(self._det.prefix, channel, roi, name=name,
                                     use_sum=self.use_sums)
            else:
                if self.limit_rois:
                    raise ValueError('Cannot add more ROIs than the EPICS layer '
                                     'supports (limit_rois is enabled)')

                logger.warning('ROI {} will be recorded in fly scans but will '
                               'not be available for live preview (num_roi={})'
                               ''.format(name, self.num_roi))

            if epics_roi is not None:
                epics_roi.set_roi(ev_low, ev_high, units='ev')

            info = ROISnapshot(chan=channel, ev_low=ev_low, ev_high=ev_high,
                               name=name, epics_roi=epics_roi)
            self._roi_config[channel][roi] = info

    @property
    def rois(self):
        '''All configured ROIs'''

        for chan, chan_rois in self._roi_config.items():
            for roi_num, roi in chan_rois.items():
                yield roi

    def get_epics_rois(self, channels=None, names=None, full_names=None):
        '''Get the EPICS ROIs which can be used in data collection

        Parameters
        ----------
        channels : list, optional
            A list of channels to match
        full_names : list, optional
            A list of full names to match, e.g., ['Det1_Si']
        names : list, optional
            A list of partial names to match, e.g., ['Si'] would match
            Det1_Si, Det2_Si, and so on.
        '''
        for roi in self.rois:
            if channels is not None and roi.chan not in channels:
                continue

            if full_names is not None and roi.name not in full_names:
                continue

            if names is not None:
                found = False
                for name in names:
                    if roi.name.endswith(name):
                        found = True
                        break

                if not found:
                    continue

            if roi.epics_roi is not None:
                yield roi.epics_roi

    def clear(self, channel, roi):
        '''Clear ROI from a specific channel by index'''
        return self.set(channel, roi, 0, 0)

    def clear_all(self, channels=None):
        '''Clear all ROIs on the specified channels

        If no channels are specified, all will be cleared.
        '''

        if channels is None:
            channels = self._roi_config.keys()

        for channel in channels:
            chan_rois = self._roi_config[channel]
            for roi_num in list(chan_rois.keys()):
                roi = chan_rois[roi_num]
                if roi.epics_roi is not None:
                    roi.epics_roi.clear()

            chan_rois.clear()

    def add(self, ev_low, ev_high, name, channels=None):
        '''Add an ROI from ev_low to ev_high on the given channels

        If a channel prefix is set, each roi name will be formatted
        accordingly.
        '''
        if channels is None:
            channels = self._det.default_channels

        for channel in channels:
            roi_num = 1
            while True:
                if self.limit_rois and roi_num > self.num_roi:
                    raise ValueError('Cannot add more ROIs than the EPICS '
                                     'layer supports (limit_rois is enabled)')

                try:
                    self._roi_config[channel][roi_num]
                except KeyError:
                    self.set(channel, roi_num, ev_low, ev_high,
                             name=self.get_roi_name(channel, name))
                    break

                roi_num += 1
