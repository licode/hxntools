from __future__ import print_function
import os
import numpy as np
import time
import logging

from ophyd.areadetector.detectors import (AreaDetector, ADSignal)
from ophyd.area_detector import AreaDetectorFileStoreTIFF
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


class TimepixFileStore(AreaDetectorFileStoreTIFF):
    def __init__(self, det, basename, **kwargs):
        super(TimepixFileStore, self).__init__(basename, cam='cam1:',
                                               **kwargs)
        self._det = det

    def _extra_AD_configuration(self):
        self._det.array_callbacks.put('Enable')
        self._det.num_images.put(1)
        self._det.tiff1.auto_increment.put(1)
        self._det.tiff1.auto_save.put(1)
        self._det.tiff1.num_capture.put(self._total_points)
        self._det.tiff1.file_write_mode.put(2)
        self._det.tiff1.enable.put(1)
        self._det.tiff1.capture.put(1)

    def deconfigure(self):
        # Wait for the last frame
        super(TimepixFileStore, self).deconfigure()

        self._total_points = None
        self._det.tiff1.capture.put(0)

    def _make_filename(self, **kwargs):
        super(TimepixFileStore, self)._make_filename(**kwargs)

        makedirs(self._store_file_path)

    def set(self, total_points=0, **kwargs):
        self._total_points = total_points


class TimepixDetector(AreaDetector):
    _html_docs = []

    tpx_corrections_dir = ADSignal('TPXCorrectionsDir', string=True)
    tpx_dac = ADSignal('TPXDAC_RBV', rw=False)
    tpx_dac_available = ADSignal('TPX_DACAvailable')
    tpx_dac_file = ADSignal('TPX_DACFile', string=True)
    tpx_dev_ip = ADSignal('TPX_DevIp', has_rbv=True)
    _tpx_extended_frame = ADSignal('TPX_ExtendedFrame', has_rbv=True)
    _tpx_extended_frame_no = ADSignal('TPX_ExtendedFrameNo')
    _tpx_extended_frame_yes = ADSignal('TPX_ExtendedFrameYes')

    @property
    def tpx_extended_frame(self):
        return self._tpx_extended_frame

    @tpx_extended_frame.setter
    def tpx_extended_frame(self, value):
        if value:
            self._tpx_extended_frame_yes.put(1)
        else:
            self._tpx_extended_frame_no.put(1)

    tpx_frame_buff_index = ADSignal('TPXFrameBuffIndex')
    tpx_hw_file = ADSignal('TPX_HWFile', string=True)
    tpx_initialize = ADSignal('TPX_Initialize', has_rbv=True)
    tpx_load_dac_file = ADSignal('TPXLoadDACFile')
    tpx_num_frame_buffers = ADSignal('TPXNumFrameBuffers', has_rbv=True)
    tpx_pix_config_file = ADSignal('TPX_PixConfigFile', string=True)
    tpx_reset_detector = ADSignal('TPX_resetDetector')

    tpx_raw_image_number = ADSignal('TPXImageNumber')
    tpx_raw_prefix = ADSignal('TPX_DataFilePrefix', string=True)
    tpx_raw_path = ADSignal('TPX_DataSaveDirectory', string=True)

    _tpx_save_to_file = ADSignal('TPX_SaveToFile', has_rbv=True)
    _tpx_save_to_file_no = ADSignal('TPX_SaveToFileNo')
    _tpx_save_to_file_yes = ADSignal('TPX_SaveToFileYes')

    @property
    def tpx_save_raw(self):
        return self._tpx_save_to_file

    @tpx_save_raw.setter
    def tpx_save_raw(self, value):
        if value:
            self._tpx_save_to_file_yes.put(1)
        else:
            self._tpx_save_to_file_no.put(1)

    tpx_start_sophy = ADSignal('TPX_StartSoPhy', has_rbv=True)
    tpx_status = ADSignal('TPXStatus_RBV', rw=False)
    tpx_sync_mode = ADSignal('TPXSyncMode', has_rbv=True)
    tpx_sync_time = ADSignal('TPXSyncTime', has_rbv=True)
    tpx_system_id = ADSignal('TPXSystemID')
    tpx_trigger = ADSignal('TPXTrigger')

    def __init__(self, prefix, file_path='', ioc_file_path='', **kwargs):
        AreaDetector.__init__(self, prefix, **kwargs)

        self.filestore = TimepixFileStore(self, self._base_prefix,
                                          stats=[], shutter=None,
                                          file_path=file_path,
                                          ioc_file_path=ioc_file_path,
                                          name=self.name)

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
