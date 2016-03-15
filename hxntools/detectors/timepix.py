from __future__ import print_function
import logging

from ophyd.areadetector.trigger_mixins import SingleTrigger
from ophyd.areadetector.filestore_mixins import (FileStoreIterativeWrite,
                                                 FileStoreTIFF)
from ophyd import (Device, Component as Cpt, AreaDetector, TIFFPlugin)
from ophyd import (Signal, EpicsSignal, EpicsSignalRO)
from ophyd.areadetector import (EpicsSignalWithRBV as SignalWithRBV, CamBase)
from .utils import makedirs


logger = logging.getLogger(__name__)


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


class TimepixDetectorCam(CamBase):
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


class TimepixDetector(SingleTrigger, AreaDetector):
    _html_docs = []

    make_directories = Cpt(Signal, value=True,
                           doc='Make directories on the DAQ side')


class TimepixTiffPlugin(TIFFPlugin, FileStoreTIFF, FileStoreIterativeWrite):
    def make_filename(self):
        fn, rp, write_path = super().make_filename()
        if self.parent.make_directories.get():
            makedirs(write_path)
        return fn, rp, write_path


class HxnTimepixDetector(TimepixDetector):
    cam = Cpt(TimepixDetectorCam, 'cam1:',
              read_attrs=[],
              configuration_attrs=['tpx_corrections_dir', 'tpx_dac',
                                   'tpx_dac_file', 'tpx_dev_ip', 'tpx_hw_file',
                                   'tpx_system_id', 'tpx_pix_config_file',
                                   ])
    tiff1 = Cpt(TimepixTiffPlugin, 'TIFF1:',
                read_attrs=[],
                configuration_attrs=[],
                write_path_template='/data/%Y/%m/%d/')

    def __init__(self, prefix, configuration_attrs=None, **kwargs):
        if configuration_attrs is None:
            configuration_attrs = ['cam', 'tiff1']
        super().__init__(prefix, configuration_attrs=configuration_attrs,
                         **kwargs)


    @property
    def count_time(self):
        return self.cam.exposure_time.value

    @count_time.setter
    def count_time(self, val):
        self.cam.exposure_time.put(val)
        self.cam.acquire_period.put(val + 0.005)
