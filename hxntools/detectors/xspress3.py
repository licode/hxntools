from __future__ import print_function
import time
import logging

# import itertools
# import filestore.api as fs_api
# from filestore.commands import bulk_insert_datum
# from .utils import makedirs

from collections import OrderedDict

import h5py

from ophyd.areadetector import (AreaDetector, CamBase,
                                EpicsSignalWithRBV as SignalWithRBV)
from ophyd import (Signal, EpicsSignal, EpicsSignalRO)

from ophyd import (Device, Component as C, FormattedComponent as FC,
                   DynamicDeviceComponent as DDC)
from ophyd.areadetector.plugins import PluginBase
from ophyd.areadetector.filestore_mixins import (FileStoreBase, new_uid)
from ophyd.areadetector.trigger_mixins import (TriggerBase, SingleTrigger)

from ..handlers import Xspress3HDF5Handler
from ..handlers.xspress3 import XRF_DATA_KEY

logger = logging.getLogger(__name__)


# class Xspress3FileStore(AreaDetectorFileStore):
#     '''Xspress3 acquisition -> filestore'''
#
#     def __init__(self, det, basename, file_template='%s%s_%6.6d.h5',
#                  config_time=0.5,
#                  mds_key_format='{self._det.name}_ch{chan}',
#                  **kwargs):
#         super().__init__(basename, cam='', reset_acquire=False,
#                          use_image_mode=False, **kwargs)
#
#         self._det = det
#         # Use the EpicsSignal file_template from the detector
#         self._file_template = det.hdf5.file_template
#         # (_file_template is used in _make_filename, etc)
#         self.file_template = file_template
#         self._filestore_res = None
#         self.channels = list(range(1, det.num_channels + 1))
#         self._total_points = None
#         self._master = None
#         self._external_trig = None
#         self._config_time = config_time
#         self.mds_keys = {chan: mds_key_format.format(self=self, chan=chan)
#                          for chan in self.channels}
#         self._file_plugin = None
#
#     def _get_datum_args(self, seq_num):
#         for chan in self.channels:
#             yield {'frame': seq_num, 'channel': chan}
#
#     def read(self):
#         timestamp = time.time()
#         uids = [str(uuid.uuid4()) for ch in self.channels]
#
#         bulk_insert_datum(self._filestore_res, uids,
#                           self._get_datum_args(self._abs_trigger_count))
#
#         self._abs_trigger_count += 1
#         return {self.mds_keys[ch]: {'timestamp': timestamp,
#                                     'value': uid,
#                                     }
#                 for uid, ch in zip(uids, self.channels)
#                 }
#
#     def bulk_read(self, timestamps):
#         channels = self.channels
#         ch_uids = {ch: [str(uuid.uuid4()) for ts in timestamps]
#                    for ch in channels}
#
#         count = len(timestamps)
#         if count == 0:
#             return {}
#
#         def get_datum_args():
#             for ch in channels:
#                 for seq_num in range(count):
#                     yield {'frame': seq_num,
#                            'channel': ch}
#
#         uids = [ch_uids[ch] for ch in channels]
#         bulk_insert_datum(self._filestore_res, itertools.chain(*uids),
#                           get_datum_args())
#
#         return {self.mds_keys[ch]: ch_uids[ch]
#                 for ch in channels
#                 }
#
#     def _make_filename(self, **kwargs):
#         super()._make_filename(**kwargs)
#
#         makedirs(self._store_file_path)
#
#     def deconfigure(self, *args, **kwargs):
#         # self._det.hdf5.capture.put(0)
#         try:
#             i = 0
#             while self._det.hdf5.capture.value == 1:
#                 i += 1
#                 if (i % 50) == 0:
#                     logger.warning('Still capturing data .... waiting.')
#                 time.sleep(0.1)
#         except KeyboardInterrupt:
#             logger.warning('Still capturing data .... interrupted.')
#
#         self._det.trigger_mode.put('Internal')
#         self._total_points = None
#         self._master = None
#
#         # TODO
#         self._old_image_mode = self._image_mode.value
#         self._old_acquire = self._acquire.value
#
#         super().deconfigure()
#
#     def set(self, total_points=0, master=None, external_trig=False,
#             **kwargs):
#         self._total_points = total_points
#         self._master = master
#         self._external_trig = external_trig
#
#     def configure(self, state=None):
#         ext_trig = (self._master is not None or self._external_trig)
#
#         logger.debug('Stopping xspress3 acquisition')
#         self._det.acquire.put(0)
#
#         time.sleep(0.1)
#
#         if ext_trig:
#             logger.debug('Setting up external triggering')
#             self._det.trigger_mode.put('TTL Veto Only')
#             if self._total_points is None:
#                 raise RuntimeError('set was not called on this detector')
#
#             self._det.num_images.put(self._total_points)
#         else:
#             logger.debug('Setting up internal triggering')
#             self._det.trigger_mode.put('Internal')
#             self._det.num_images.put(1)
#
#         logger.debug('Configuring other filestore stuff')
#         super(Xspress3FileStore, self).configure(state=state)
#
#         logger.debug('Making the filename')
#         self._make_filename(seq=0)
#
#         logger.debug('Setting up hdf5 plugin: ioc path: %s filename: %s',
#                      self._ioc_file_path, self._filename)
#         self._det.hdf5.file_template.put(self.file_template, wait=True)
#         self._det.hdf5.file_number.put(0)
#         self._det.hdf5.blocking_callbacks.put(1)
#         self._det.hdf5.enable.put(1)
#         self._det.hdf5.file_path.put(self._ioc_file_path, wait=True)
#         self._det.hdf5.file_name.put(self._filename, wait=True)
#
#         if not self._det.hdf5.file_path_exists.value:
#             raise IOError("Path {} does not exits on IOC!! Please Check"
#                           .format(self._det.hdf5.file_path.value))
#
#         logger.debug('Inserting the filestore resource')
#         self._filestore_res = self._insert_fs_resource()
#
#         logger.debug('Erasing old spectra')
#         self._det.xs_erase.put(1)
#         self._det.hdf5.capture.put(1, wait=False)
#
#         if ext_trig:
#             logger.debug('Starting acquisition (waiting for triggers)')
#             self._det.acquire.put(1, wait=False)
#
#         # Xspress3 needs a bit of time to configure itself...
#         time.sleep(self._config_time)
#
#     @property
#     def count_time(self):
#         return self._det.acquire_period.value
#
#     @count_time.setter
#     def count_time(self, val):
#         self._det.acquire_period.put(val)
#
#     def acquire(self, **kwargs):
#         status = DetectorStatus(self)
#         status._finished()
#         # scaler/zebra take care of timing
#         return status
#
#     def describe(self):
#         # TODO: describe is called prior to configure, so the filestore
#         #       resource
#         #       is not yet generated
#         size = (self._det.hdf5.width.value, )
#
#         spec_desc = {'external': 'FILESTORE:',
#                      'dtype': 'array',
#                      'shape': size,
#                      }
#
#         if self._filestore_res is not None:
#             source = 'FileStore:{0.id!s}'.format(self._filestore_res)
#         else:
#             source = 'FileStore:'
#
#         spec_desc['source'] = source
#
#         desc = {}
#         for chan in self.channels:
#             desc['{}_ch{}'.format(self._det.name, chan)] = spec_desc
#
#         return desc
#
#     def _insert_fs_resource(self):
#         return fs_api.insert_resource(Xspress3HDF5Handler.HANDLER_NAME,
#                                       self.store_filename, {})
#
#     @property
#     def store_filename(self):
#         return self._store_filename
#
#     @property
#     def ioc_filename(self):
#         return self._ioc_filename


class Xspress3ExternalTrigger(SingleTrigger):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, image_name='xspress3', **kwargs)


class Xspress3DetectorCam(CamBase):
    '''Quantum Detectors Xspress3 detector'''
    xs_config_path = C(SignalWithRBV, 'CONFIG_PATH')
    xs_config_save_path = C(SignalWithRBV, 'CONFIG_SAVE_PATH')
    xs_connect = C(EpicsSignal, 'CONNECT')
    xs_connected = C(EpicsSignal, 'CONNECTED')
    xs_ctrl_dtc = C(SignalWithRBV, 'CTRL_DTC')
    xs_ctrl_mca_roi = C(SignalWithRBV, 'CTRL_MCA_ROI')
    xs_debounce = C(SignalWithRBV, 'DEBOUNCE')
    xs_disconnect = C(EpicsSignal, 'DISCONNECT')
    xs_erase = C(EpicsSignal, 'ERASE')
    xs_erase_array_counters = C(EpicsSignal, 'ERASE_ArrayCounters')
    xs_erase_attr_reset = C(EpicsSignal, 'ERASE_AttrReset')
    xs_erase_proc_reset_filter = C(EpicsSignal, 'ERASE_PROC_ResetFilter')
    xs_frame_count = C(EpicsSignalRO, 'FRAME_COUNT_RBV')
    xs_hdf_capture = C(EpicsSignalRO, 'HDF5:Capture_RBV')
    xs_hdf_num_capture_calc = C(EpicsSignal, 'HDF5:NumCapture_CALC')
    xs_invert_f0 = C(SignalWithRBV, 'INVERT_F0')
    xs_invert_veto = C(SignalWithRBV, 'INVERT_VETO')
    xs_max_frames = C(EpicsSignalRO, 'MAX_FRAMES_RBV')
    xs_max_frames_driver = C(EpicsSignalRO, 'MAX_FRAMES_DRIVER_RBV')
    xs_max_num_channels = C(EpicsSignalRO, 'MAX_NUM_CHANNELS_RBV')
    xs_max_spectra = C(SignalWithRBV, 'MAX_SPECTRA')
    xs_name = C(EpicsSignal, 'NAME')
    xs_num_cards = C(EpicsSignalRO, 'NUM_CARDS_RBV')
    xs_num_channels = C(SignalWithRBV, 'NUM_CHANNELS')
    xs_num_frames_config = C(SignalWithRBV, 'NUM_FRAMES_CONFIG')
    xs_reset = C(EpicsSignal, 'RESET')
    xs_restore_settings = C(EpicsSignal, 'RESTORE_SETTINGS')
    xs_run_flags = C(SignalWithRBV, 'RUN_FLAGS')
    xs_save_settings = C(EpicsSignal, 'SAVE_SETTINGS')
    xs_trigger = C(EpicsSignal, 'TRIGGER')
    xs_update = C(EpicsSignal, 'UPDATE')
    xs_update_attr = C(EpicsSignal, 'UPDATE_AttrUpdate')


def ev_to_bin(ev):
    '''Convert eV to bin number'''
    return int(ev / 10)


def bin_to_ev(bin_):
    '''Convert bin number to eV'''
    return int(bin_) * 10


class DerivedSignal(Signal):
    '''A signal which is derived from another one'''
    def __init__(self, derived_from, **kwargs):
        self._derived_from = derived_from
        super().__init__(**kwargs)

    def describe(self):
        desc = self._derived_from.describe()[self._derived_from.name]
        return {self.name: desc}

    def get(self, **kwargs):
        return self._derived_from.get(**kwargs)

    def put(self, value, **kwargs):
        return self._derived_from.put(value, **kwargs)


class EvSignal(DerivedSignal):
    '''A signal that converts a bin number into electron volts'''
    def __init__(self, parent_attr, *, parent=None, **kwargs):
        bin_signal = getattr(parent, parent_attr)
        super().__init__(derived_from=bin_signal, parent=parent, **kwargs)

    def get(self, **kwargs):
        bin_ = super().get(**kwargs)
        return bin_to_ev(bin_)

    def put(self, ev_value, **kwargs):
        bin_value = ev_to_bin(ev_value)
        return super().put(bin_value, **kwargs)

    def describe(self):
        desc = super().describe()
        desc[self.name]['units'] = 'eV'
        return desc


class Xspress3ROISettings(PluginBase):
    '''Full areaDetector plugin settings'''
    pass


class Xspress3ROI(Device):
    '''A configurable Xspress3 EPICS ROI'''

    # prefix: C{channel}_   MCA_ROI{self.roi_num}
    bin_low = FC(SignalWithRBV, '{self.channel.prefix}{self.bin_suffix}_LLM')
    bin_high = FC(SignalWithRBV, '{self.channel.prefix}{self.bin_suffix}_HLM')

    # derived from the bin signals, low and high electron volt settings:
    ev_low = C(EvSignal, parent_attr='bin_low')
    ev_high = C(EvSignal, parent_attr='bin_high')

    # C{channel}_  ROI{self.roi_num}
    value = C(EpicsSignalRO, 'Value_RBV')
    value_sum = C(EpicsSignalRO, 'ValueSum_RBV')

    enable = C(SignalWithRBV, 'EnableCallbacks')
    # ad_plugin = C(Xspress3ROISettings, '')

    def __init__(self, prefix, *, roi_num=0, use_sum=False,
                 read_attrs=None, configuration_attrs=None, parent=None,
                 bin_suffix=None, **kwargs):

        if read_attrs is None:
            if use_sum:
                read_attrs = ['value_sum']
            else:
                read_attrs = ['value', 'value_sum']

        if configuration_attrs is None:
            configuration_attrs = ['ev_low', 'ev_high', 'enable']

        rois = parent
        channel = rois.parent
        self._channel = channel
        self._roi_num = roi_num
        self._use_sum = use_sum
        self._ad_plugin = getattr(rois, 'ad_attr{:02d}'.format(roi_num))

        if bin_suffix is None:
            bin_suffix = 'MCA_ROI{}'.format(roi_num)

        self.bin_suffix = bin_suffix

        super().__init__(prefix, parent=parent, read_attrs=read_attrs,
                         configuration_attrs=configuration_attrs, **kwargs)

    @property
    def channel(self):
        '''The Xspress3Channel instance associated with the ROI'''
        return self._channel

    @property
    def channel_num(self):
        '''The channel number associated with the ROI'''
        return self._channel.channel_num

    @property
    def roi_num(self):
        '''The ROI number'''
        return self._roi_num

    def clear(self):
        '''Clear and disable this ROI'''
        self.configure(0, 0)

    def configure(self, ev_low, ev_high):
        '''Configure the ROI with low and high eV

        Parameters
        ----------
        ev_low : int
            low electron volts for ROI
        ev_high : int
            high electron volts for ROI
        '''
        ev_low = int(ev_low)
        ev_high = int(ev_high)

        enable = 1 if ev_high > ev_low else 0
        changed = any([self.ev_high.get() != ev_high,
                       self.ev_low.get() != ev_low,
                       self.enable.get() != enable])

        if not changed:
            return

        logger.debug('Setting up EPICS ROI: name=%s ev=(%s, %s) '
                     'enable=%s prefix=%s channel=%s',
                     self.name, ev_low, ev_high, enable, self._prefix,
                     self._channel)
        if ev_high <= self.ev_low.get():
            self.ev_low.put(0)

        self.ev_high.put(ev_high)
        self.ev_low.put(ev_low)
        self.enable.put(enable)


# class Xspress3SoftROI(Device):
#     '''An ROI beyond what can be represented on the EPICS level'''
#     bin_low = C(Signal)
#     bin_high = C(Signal)
#
#     # derived from the bin signals, low and high electron volt settings:
#     ev_low = C(EvSignal, parent_attr='bin_low')
#     ev_high = C(EvSignal, parent_attr='bin_high')
#
#     data = C(Signal)
#
#     def read(self):
#         raise RuntimeError('A SoftROI cannot be used in data acquisition')
#
#     describe = read
#

def make_rois(rois):
    defn = OrderedDict()
    for roi in rois:
        attr = 'roi{:02d}'.format(roi)
        #             cls          prefix                kwargs
        defn[attr] = (Xspress3ROI, 'ROI{}:'.format(roi), dict(roi_num=roi))
        # e.g., device.rois.roi01 = Xspress3ROI('ROI1:', roi_num=1)

        # AreaDetector NDPluginAttribute information
        attr = 'ad_attr{:02d}'.format(roi)
        defn[attr] = (Xspress3ROISettings, 'ROI{}:'.format(roi), {})
        # e.g., device.rois.roi01 = Xspress3ROI('ROI1:', roi_num=1)

        # TODO: 'roi01' and 'ad_attr_01' have the same prefix and could
        # technically be combined. Is this desirable?

    defn['num_rois'] = (Signal, None, dict(value=len(rois)))
    # e.g., device.rois.num_rois.get() => 16
    return defn


class Xspress3Channel(Device):
    roi_name_format = 'Det{self.channel_num}_{roi_name}'

    rois = DDC(make_rois(range(1, 17)))
    vis_enabled = C(EpicsSignal, 'PluginControlVal')

    def __init__(self, prefix, *, channel_num=None, **kwargs):
        self.channel_num = int(channel_num)

        super().__init__(prefix, **kwargs)

    @property
    def all_rois(self):
        for roi in range(1, self.rois.num_rois.get() + 1):
            yield getattr(self.rois, 'roi{:02d}'.format(roi))

    def set_roi(self, index, ev_low, ev_high, *, name=None):
        '''Set specified ROI to (ev_low, ev_high)

        Parameters
        ----------
        index : int or Xspress3ROI
            The roi index or instance to set
        ev_low : int
            low eV setting
        ev_high : int
            high eV setting
        name : str, optional
            The unformatted ROI name to set. Each channel specifies its own
                channel.roi_name_format = 'Det{self.channel_num}_{roi_name}'
            in which the name parameter will get expanded.
        '''
        if isinstance(index, Xspress3ROI):
            roi = index
        else:
            roi = list(self.all_rois)[index]

        roi.configure(ev_low, ev_high)
        if name is not None:
            roi.name = self.roi_name_format.format(self=self, roi_name=name)

    def clear_all_rois(self):
        '''Clear all ROIs'''
        for roi in self.all_rois:
            roi.clear()


class Xspress3Detector(AreaDetector):
    cam = C(Xspress3DetectorCam, '')
    # hdf5 = C(Xspress3HDFPlugin, '')

    # XF:03IDC-ES{Xsp:1}           C1_   ...
    channel1 = C(Xspress3Channel, 'C1_', channel_num=1)

    data_key = XRF_DATA_KEY

    def __init__(self, prefix, *, read_attrs=None, configuration_attrs=None,
                 monitor_attrs=None, name=None, parent=None,
                 # to remove?
                 file_path='', ioc_file_path='', default_channels=None,
                 channel_prefix=None,
                 roi_sums=False,
                 # to remove?
                 **kwargs):

        if read_attrs is None:
            read_attrs = ['channel1']

        if configuration_attrs is None:
            configuration_attrs = ['channel1.rois',
                                   'cam.xs_config_path',
                                   'cam.xs_config_save_path',
                                   'cam.xs_connected', 'cam.xs_ctrl_dtc',
                                   'cam.xs_ctrl_mca_roi', 'cam.xs_debounce',
                                   'cam.xs_erase', 'cam.xs_frame_count',
                                   'cam.xs_hdf_capture',
                                   'cam.xs_hdf_num_capture_calc',
                                   'cam.xs_invert_f0', 'cam.xs_invert_veto',
                                   'cam.xs_max_frames',
                                   'cam.xs_max_frames_driver',
                                   'cam.xs_max_num_channels',
                                   'cam.xs_max_spectra', 'cam.xs_name',
                                   'cam.xs_num_cards', 'cam.xs_num_channels',
                                   'cam.xs_num_frames_config', 'cam.xs_reset',
                                   'cam.xs_restore_settings',
                                   'cam.xs_run_flags', 'cam.xs_save_settings']

        super().__init__(prefix, read_attrs=read_attrs,
                         configuration_attrs=configuration_attrs,
                         monitor_attrs=monitor_attrs,
                         name=name, parent=parent, **kwargs)

        # get all sub-device instances
        sub_devices = {attr: getattr(self, attr)
                       for attr in self._sub_devices}

        # filter those sub-devices, just giving channels
        channels = {dev.channel_num: dev
                    for attr, dev in sub_devices.items()
                    if isinstance(dev, Xspress3Channel)
                    }

        # make an ordered dictionary with the channels in order
        self._channels = OrderedDict(sorted(channels.items()))

    @property
    def channels(self):
        return self._channels.copy()

    @property
    def all_rois(self):
        for ch_num, channel in self._channels.items():
            for roi in channel.all_rois:
                yield roi

    @property
    def enabled_rois(self):
        for roi in self.all_rois:
            if roi.enable.get():
                yield roi

    def open_hdf5_wait(self, fn, *, max_retries=2, try_stop=False):
        '''Wait for the HDF5 file specified to be closed'''
        det = self._det
        warned = False
        retry = 0
        while retry < max_retries:
            retry += 1
            try:
                return h5py.File(fn, 'r')
            except (IOError, OSError):
                if not warned:
                    logger.error('Xspress3 hdf5 file still open; press '
                                 'Ctrl-C to cancel')
                    warned = True

                if try_stop:
                    time.sleep(2.0)
                    det.hdf5.capture.put(0)
                    det.acquire.put(0)
            except KeyboardInterrupt:
                raise RuntimeError('Unable to open HDF5 file; interrupted '
                                   'by Ctrl-C')
            else:
                if warned:
                    logger.info('Xspress3 hdf5 file opened')
                break

        if retry >= max_retries:
            raise RuntimeError('Unable to open HDF5 file; exceeded maximum '
                               'retries')

    def read_hdf5(self, fn, *, rois=None, max_retries=2):
        '''Read ROI data from an HDF5 file using the current ROI configuration

        Parameters
        ----------
        fn : str
            HDF5 filename to load
        rois : sequence of Xspress3ROI instances, optional

        '''
        if rois is None:
            rois = self.enabled_rois

        num_points = self.cam.num_images.get()
        hdf = self.open_hdf5_wait(fn, max_retries=max_retries,
                                  try_stop=False)

        RoiTuple = Xspress3ROI.get_device_tuple()

        handler = Xspress3HDF5Handler(hdf, key=self.data_key)
        for roi in self.enabled_rois:
            roi_data = handler.get_roi(chan=roi.channel_num,
                                       bin_low=roi.bin_low.get(),
                                       bin_high=roi.bin_high.get(),
                                       max_points=num_points)

            roi_info = RoiTuple(bin_low=roi.bin_low.get(),
                                bin_high=roi.bin_high.get(),
                                ev_low=roi.ev_low.get(),
                                ev_high=roi.ev_high.get(),
                                value=roi_data,
                                value_sum=None)

            yield roi.name, roi_info


class HxnXspress3Detector(Xspress3Detector):
    channel1 = C(Xspress3Channel, 'C1_', channel_num=1)
    channel2 = C(Xspress3Channel, 'C2_', channel_num=2)
    channel3 = C(Xspress3Channel, 'C3_', channel_num=3)

    # Currently only using three channels. Uncomment these to enable more
    # channels:
    # channel4 = C(Xspress3Channel, 'C4_', channel_num=4)
    # channel5 = C(Xspress3Channel, 'C5_', channel_num=5)
    # channel6 = C(Xspress3Channel, 'C6_', channel_num=6)
    # channel7 = C(Xspress3Channel, 'C7_', channel_num=7)
    # channel8 = C(Xspress3Channel, 'C8_', channel_num=8)
