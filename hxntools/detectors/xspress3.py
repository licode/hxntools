from __future__ import print_function, division
import time
import time as ttime
import logging
import itertools
import uuid

# import itertools
import filestore.api as fs_api
from filestore.commands import bulk_insert_datum
from .utils import (makedirs, DerivedSignal)

from collections import OrderedDict

import h5py

from ophyd.areadetector import (DetectorBase,
                                EpicsSignalWithRBV as SignalWithRBV)
from ophyd import (Signal, EpicsSignal, EpicsSignalRO)

from ophyd import (Device, Component as C, FormattedComponent as FC,
                   DynamicDeviceComponent as DDC)
from ophyd.areadetector.plugins import PluginBase
from ophyd.areadetector.filestore_mixins import FileStorePluginBase

from ophyd.areadetector.plugins import HDF5Plugin
from ophyd.device import BlueskyInterface, Staged, Component as Cpt
from ophyd.ophydobj import DeviceStatus

from ..handlers import Xspress3HDF5Handler
from ..handlers.xspress3 import XRF_DATA_KEY

logger = logging.getLogger(__name__)


def ev_to_bin(ev):
    '''Convert eV to bin number'''
    return int(ev / 10)


def bin_to_ev(bin_):
    '''Convert bin number to eV'''
    return int(bin_) * 10


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


class PermissiveGetSignal(Signal):
    def get(self, use_monitor=None):
        return super().get()


class Xspress3FileStore(FileStorePluginBase, HDF5Plugin):
    '''Xspress3 acquisition -> filestore'''

    def __init__(self, basename,
                 config_time=0.5,
                 mds_key_format='{self._settings.name}_ch{chan}',
                 parent=None,
                 **kwargs):
        super().__init__(basename,
                         parent=parent,
                         **kwargs)
        det = parent
        self._settings = det.settings
        # Use the EpicsSignal file_template from the detector
        self.stage_sigs[self.blocking_callbacks] = 1
        self.stage_sigs[self.enable] = 1

        self._filestore_res = None
        self.channels = list(range(1, len([_ for _ in det.signal_names
                                           if _.startswith('chan')]) + 1))
        # this was in original code, but I kinda-sorta nuked because
        # it was not needed for SRX and I could not guess what it did
        self._master = None

        self._config_time = config_time
        self.mds_keys = {chan: mds_key_format.format(self=self, chan=chan)
                         for chan in self.channels}

    def _get_datum_args(self, seq_num):
        for chan in self.channels:
            yield {'frame': seq_num, 'channel': chan}

    def read(self):
        timestamp = time.time()
        uids = [str(uuid.uuid4()) for ch in self.channels]

        bulk_insert_datum(self._filestore_res, uids,
                          self._get_datum_args(self.parent._abs_trigger_count))
        # print(self._get_datum_args(self.parent._abs_trigger_count))

        return {self.mds_keys[ch]: {'timestamp': timestamp,
                                    'value': uid,
                                    }
                for uid, ch in zip(uids, self.channels)
                }

    def kickoff(self):
        # TODO
        raise NotImplementedError()

    def collect(self):
        # TODO
        raise NotImplementedError()
        channels = self.channels
        timestamps = None  # TODO TAC
        ch_uids = {ch: [str(uuid.uuid4()) for ts in timestamps]
                   for ch in channels}

        count = len(timestamps)
        if count == 0:
            return {}

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

    def make_filename(self):
        fn, rp, write_path = super().make_filename()

        if self.parent.make_directories.get():
            makedirs(write_path)
        return fn, rp, write_path

    def unstage(self):
        try:
            i = 0
            # this needs a fail-safe, RE will now hang forever here
            # as we eat all SIGINT to ensure that cleanup happens in
            # orderly manner.
            while self.capture.value == 1:
                i += 1
                if (i % 50) == 0:
                    logger.warning('Still capturing data .... waiting.')
                time.sleep(0.1)
                if i > 150:
                    logger.warning('Still capturing data .... giving up.')
                    self.capture.put(0)
                    break

        except KeyboardInterrupt:
            logger.warning('Still capturing data .... interrupted.')

        return super().unstage()

    def stage(self):
        # if should external trigger
        ext_trig = self.parent.external_trig.get()
        # TODO check self._master / self.master.get()?

        logger.debug('Stopping xspress3 acquisition')
        # really force it to stop acquiring
        self._settings.acquire.put(0, wait=True)

        total_points = self.parent.total_points.get()
        spec_per_point = self.parent.spectra_per_point.get()
        total_capture = total_points * spec_per_point

        # re-order the stage signals and disable the calc record which is
        # interfering with the capture count
        self.stage_sigs.pop(self.num_capture, None)
        self.stage_sigs.pop(self._settings.num_images, None)
        self.stage_sigs[self._settings.xs_hdf_num_capture_calc_disable] = 1

        if ext_trig:
            # TODO some self._master logic went here?
            logger.debug('Setting up external triggering')
            self.stage_sigs[self._settings.trigger_mode] = 'TTL Veto Only'
            self.stage_sigs[self._settings.num_images] = total_capture
        else:
            logger.debug('Setting up internal triggering')
            # self._settings.trigger_mode.put('Internal')
            # self._settings.num_images.put(1)
            self.stage_sigs[self._settings.trigger_mode] = 'Internal'
            self.stage_sigs[self._settings.num_images] = spec_per_point

        self.stage_sigs[self.auto_save] = 'No'
        logger.debug('Configuring other filestore stuff')

        logger.debug('Making the filename')
        filename, read_path, write_path = self.make_filename()

        logger.debug('Setting up hdf5 plugin: ioc path: %s filename: %s',
                     write_path, filename)

        if not self.parent.hdf5.file_path_exists.value:
            raise IOError("Path {} does not exits on IOC!! Please Check"
                          .format(self._settings.hdf5.file_path.value))

        logger.debug('Erasing old spectra')
        self._settings.xs_erase.put(1, wait=True)

        if ext_trig:
            logger.debug('Starting acquisition (waiting for triggers)')
            self.stage_sigs[self._settings.acquire] = 1

        # this must be set after self._settings.num_images because at the Epics
        # layer  there is a helpful link that sets this equal to that (but
        # not the other way)
        self.stage_sigs[self.num_capture] = total_capture

        # actually apply the stage_sigs
        ret = super().stage()

        logger.debug('Inserting the filestore resource')
        self._filestore_res = fs_api.insert_resource(
            Xspress3HDF5Handler.HANDLER_NAME, self._fn, {})

        # this gets auto turned off at the end
        self.capture.put(1)

        # Xspress3 needs a bit of time to configure itself...
        # this does not play nice with the event loop :/
        time.sleep(self._config_time)

        return ret

    def configure(self, total_points=0, master=None, external_trig=False,
                  **kwargs):
        raise NotImplementedError()

    @property
    def count_time(self):
        return self._settings.acquire_period.value

    @count_time.setter
    def count_time(self, val):
        self._settings.acquire_period.put(val)

    def describe(self):
        # should this use a better value?
        size = (self._settings.hdf5.width.get(), )

        spec_desc = {'external': 'FILESTORE:',
                     'dtype': 'array',
                     'shape': size,
                     }
        # shouldn't the source be the array PV?
        if self._filestore_res is not None:
            source = 'FileStore::{0.id!s}'.format(self._filestore_res)
        else:
            source = 'FileStore:'

        spec_desc['source'] = source

        desc = {}
        for chan in self.channels:
            desc['{}_ch{}'.format(self._settings.name, chan)] = spec_desc

        return desc


class Xspress3DetectorSettings(Device):
    '''Quantum Detectors Xspress3 detector'''
    acquire = C(EpicsSignal, 'Acquire')
    trigger_mode = C(EpicsSignal, 'TriggerMode')
    num_images = C(SignalWithRBV, 'NumImages')
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
    xs_hdf_num_capture_calc_disable = C(EpicsSignal,
                                        'HDF5:NumCapture_CALC.DISA')
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
    array_callbacks = C(SignalWithRBV, 'ArrayCallbacks')


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
            # configuration_attrs = ['ev_low', 'ev_high', 'enable']
            configuration_attrs = ['enable']

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


def make_rois(rois):
    defn = OrderedDict()
    for roi in rois:
        attr = 'roi{:02d}'.format(roi)
        #             cls          prefix                kwargs
        defn[attr] = (Xspress3ROI, 'ROI{}:'.format(roi), dict(roi_num=roi))
        # e.g., device.rois.roi01 = Xspress3ROI('ROI1:', roi_num=1)

        # AreaDetector NDPluginAttribute information
        attr = 'ad_attr{:02d}'.format(roi)
        defn[attr] = (Xspress3ROISettings, 'ROI{}:'.format(roi),
                      dict(read_attrs=[]))
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


class Xspress3Detector(DetectorBase):
    settings = C(Xspress3DetectorSettings, '')

    external_trig = Cpt(PermissiveGetSignal, value=False,
                        doc='Use external triggering')
    total_points = Cpt(PermissiveGetSignal, value=2,
                       doc='The total number of points to acquire overall')
    spectra_per_point = Cpt(PermissiveGetSignal, value=1,
                            doc='Number of spectra per point')
    make_directories = Cpt(Signal, value=False,
                           doc='Make directories on the DAQ side')

    # XF:03IDC-ES{Xsp:1}           C1_   ...
    # channel1 = C(Xspress3Channel, 'C1_', channel_num=1)

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
            read_attrs = ['channel1', ]

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
                    self.hdf5.capture.put(0)
                    self.acquire.put(0)
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

        num_points = self.settings.num_images.get()
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
                                value_sum=None,
                                enable=None)

            yield roi.name, roi_info


class XspressTrigger(BlueskyInterface):
    """Base class for trigger mixin classes

    Subclasses must define a method with this signature:

    `acquire_changed(self, value=None, old_value=None, **kwargs)`
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # settings
        self._status = None
        self._acquisition_signal = self.settings.acquire
        self._abs_trigger_count = 0

    def stage(self):
        self._abs_trigger_count = 0
        self._acquisition_signal.subscribe(self._acquire_changed)
        super().stage()

    def unstage(self):
        super().unstage()
        self._acquisition_signal.clear_sub(self._acquire_changed)

    def _acquire_changed(self, value=None, old_value=None, **kwargs):
        "This is called when the 'acquire' signal changes."
        if self._status is None:
            return
        if (old_value == 1) and (value == 0):
            # Negative-going edge means an acquisition just finished.
            self._status._finished()

    def trigger(self):
        if self._staged != Staged.yes:
            raise RuntimeError("not staged")

        self._status = DeviceStatus(self)
        self._acquisition_signal.put(1, wait=False)
        trigger_time = ttime.time()

        for sn in self.read_attrs:
            if sn.startswith('channel'):
                ch = getattr(self, sn)
                self.dispatch(ch.name, trigger_time)
        return self._status


class HxnXspress3Detector(XspressTrigger, Xspress3Detector):
    channel1 = C(Xspress3Channel, 'C1_', channel_num=1)
    channel2 = C(Xspress3Channel, 'C2_', channel_num=2)
    channel3 = C(Xspress3Channel, 'C3_', channel_num=3)

    hdf5 = Cpt(Xspress3FileStore, 'HDF5:',
               read_path_template='/data/XSPRESS3/',
               write_path_template='/epics/data/')

    def __init__(self, prefix, *, configuration_attrs=None, read_attrs=None,
                 **kwargs):
        if configuration_attrs is None:
            configuration_attrs = ['external_trig', 'total_points',
                                   'spectra_per_point']
        if read_attrs is None:
            read_attrs = ['channel1', 'channel2', 'channel3', 'hdf5']
        super().__init__(prefix, configuration_attrs=configuration_attrs,
                         read_attrs=read_attrs, **kwargs)

    # Currently only using three channels. Uncomment these to enable more
    # channels:
    # channel4 = C(Xspress3Channel, 'C4_', channel_num=4)
    # channel5 = C(Xspress3Channel, 'C5_', channel_num=5)
    # channel6 = C(Xspress3Channel, 'C6_', channel_num=6)
    # channel7 = C(Xspress3Channel, 'C7_', channel_num=7)
    # channel8 = C(Xspress3Channel, 'C8_', channel_num=8)
