from __future__ import print_function
import os
import numpy as np
import time
import logging

from ophyd import (Device, Component as Cpt,
                   FormattedComponent as FC,
                   AreaDetector)
from ophyd import (EpicsSignal, EpicsSignalRO, DeviceStatus)
from ophyd.areadetector import (EpicsSignalWithRBV as SignalWithRBV)
from ophyd.utils import set_and_wait
from .utils import makedirs


logger = logging.getLogger(__name__)


class TpxRawLog(object):
    def write(self, text):
        print(text.strip())

USE_TPX_RAW = False
if USE_TPX_RAW:
    import pympx
    _tpx_buf = TpxRawLog()
    _tpx_raw_log = pympx.MpxFileLogger(_tpx_buf)
    _tpx_raw = pympx.MpxModule(0, 3, 0, pympx.MPIX_ROWS, 0, _tpx_raw_log)


# class TimepixFileStore(AreaDetectorFileStoreTIFF):
#     def __init__(self, det, basename, **kwargs):
#         super(TimepixFileStore, self).__init__(basename, cam='cam1:',
#                                                **kwargs)
#         self._det = det
#
#     def _extra_AD_configuration(self):
#         self._det.array_callbacks.put('Enable')
#         self._det.num_images.put(1)
#         self._det.tiff1.auto_increment.put(1)
#         self._det.tiff1.auto_save.put(1)
#         self._det.tiff1.num_capture.put(self._total_points)
#         self._det.tiff1.file_write_mode.put(2)
#         self._det.tiff1.enable.put(1)
#         self._det.tiff1.capture.put(1)
#
#     def deconfigure(self):
#         # Wait for the last frame
#         super(TimepixFileStore, self).deconfigure()
#
#         self._total_points = None
#         self._det.tiff1.capture.put(0)
#
#     def _make_filename(self, **kwargs):
#         super(TimepixFileStore, self)._make_filename(**kwargs)
#
#         makedirs(self._store_file_path)
#
#     def set(self, total_points=0, **kwargs):
#         self._total_points = total_points


class ValueAndSets(Device):
    def __init__(self, prefix, *, read_attrs=None, **kwargs):
        if read_attrs is None:
            read_attrs = ['value']

        super().__init__(prefix, read_attrs=read_attrs, **kwargs)

    def get(self, **kwargs):
        return self.value.get(**kwargs)

    def put(self, value, **kwargs):
        if value:
            self.set_yes.put(1, **kwargs)
        else:
            self.set_no.put(1, **kwargs)


class TpxExtendedFrame(ValueAndSets):
    value = Cpt(SignalWithRBV, 'TPX_ExtendedFrame')
    set_no = Cpt(EpicsSignal, 'TPX_ExtendedFrameNo')
    set_yes = Cpt(EpicsSignal, 'TPX_ExtendedFrameYes')


class TpxSaveRaw(ValueAndSets):
    value = Cpt(SignalWithRBV, 'TPX_SaveToFile')
    set_no = Cpt(EpicsSignal, 'TPX_SaveToFileNo')
    set_yes = Cpt(EpicsSignal, 'TPX_SaveToFileYes')


class TimepixDetector(AreaDetector):
    _html_docs = []

    tpx_corrections_dir = Cpt(EpicsSignal, 'TPXCorrectionsDir', string=True)
    tpx_dac = Cpt(EpicsSignalRO, 'TPXDAC_RBV')
    tpx_dac_available = Cpt(EpicsSignal, 'TPX_DACAvailable')
    tpx_dac_file = Cpt(EpicsSignal, 'TPX_DACFile', string=True)
    tpx_dev_ip = Cpt(SignalWithRBV, 'TPX_DevIp')

    tpx_frame_buff_index = Cpt(EpicsSignal, 'TPXFrameBuffIndex')
    tpx_hw_file = Cpt(EpicsSignal, 'TPX_HWFile', string=True)
    tpx_initialize = Cpt(SignalWithRBV, 'TPX_Initialize')
    tpx_load_dac_file = Cpt(EpicsSignal, 'TPXLoadDACFile')
    tpx_num_frame_buffers = Cpt(SignalWithRBV, 'TPXNumFrameBuffers')
    tpx_pix_config_file = Cpt(EpicsSignal, 'TPX_PixConfigFile', string=True)
    tpx_reset_detector = Cpt(EpicsSignal, 'TPX_resetDetector')

    tpx_raw_image_number = Cpt(EpicsSignal, 'TPXImageNumber')
    tpx_raw_prefix = Cpt(EpicsSignal, 'TPX_DataFilePrefix', string=True)
    tpx_raw_path = Cpt(EpicsSignal, 'TPX_DataSaveDirectory', string=True)

    tpx_start_sophy = Cpt(SignalWithRBV, 'TPX_StartSoPhy')
    tpx_status = Cpt(EpicsSignalRO, 'TPXStatus_RBV')
    tpx_sync_mode = Cpt(SignalWithRBV, 'TPXSyncMode')
    tpx_sync_time = Cpt(SignalWithRBV, 'TPXSyncTime')
    tpx_system_id = Cpt(EpicsSignal, 'TPXSystemID')
    tpx_trigger = Cpt(EpicsSignal, 'TPXTrigger')

    def __init__(self, prefix, file_path='', ioc_file_path='', **kwargs):
        super().__init__(prefix, **kwargs)

        # self.filestore = TimepixFileStore(self, self._base_prefix,
        #                                   stats=[], shutter=None,
        #                                   file_path=file_path,
        #                                   ioc_file_path=ioc_file_path,
        #                                   name=self.name)


class HxnTimepixDetector(TimepixDetector):
    def fly_configure(self, path, prefix, num_points,
                      raw=False, external_trig=True, create_dirs=True):
        # NOTE: due to timepix IOC-related issues, can't use external
        # triggering reliably, so step scan and fly scan configuration
        # are different
        if not external:
            raise NotImplementedError('TODO')

        if self.acquire.value:
            self.acquire.put(0)
            time.sleep(0.1)

        self.array_callbacks.put('Enable')

        if create_dirs:
            try:
                os.makedirs(path)
            except OSError:
                pass

        # timepix 1 external triggering
        self.trigger_mode.put(1)

        if raw:
            # setup raw file saving (buggy IOC currently)
            self.tpx_save_raw = 0
            time.sleep(0.1)

            self.image_mode = 'Multiple'
            self.tpx_raw_path = path + '/'
            self.tpx_raw_prefix = prefix
            self.num_images.put(num_points + 1)

            self.tpx_save_raw = 1
            time.sleep(0.1)
        else:
            # setup the tiff plugin
            self.tpx_save_raw = 0

            self.tiff1.enable.put(1)
            self.tiff1.file_path.put(path)
            self.tiff1.file_name.put(prefix)
            self.tiff1.file_number.put(0)
            self.tiff1.auto_save.put(1)

        self.acquire.put(1)

    def fly_deconfigure(self):
        if self.tpx_save_raw.value == 1:
            self.tpx_save_raw = 0
            # self.dump_raw_files()
        else:
            self.acquire.put(0)
            # timepix1.trigger_mode.put(0)  # internal
            # timepix1.image_mode = 'Continuous'

    def dump_raw_files(self):
        raise NotImplementedError()

        # TODO: filenames, etc are wrong
        # timepix raw file *saving* does not work reliably
        logger.debug('Timepix 1 file: %s', self.tpx1_file)

        if not os.path.exists(self.tpx1_file):
            logger.error('Timepix 1 did not save raw data file')
            return

        with open(self.tpx1_file, 'rb') as inputf:
            for i, (frame, lost_rows) in enumerate(_tpx_raw.read_frames(inputf)):
                print('Frame %d (lost_rows=%s)' % (i, lost_rows))
                print('nonzero pixels: %d' % len(frame[np.where(frame > 0)]))
