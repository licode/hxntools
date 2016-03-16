import logging

import filestore.api as fsapi
from ophyd.areadetector.filestore_mixins import (FileStoreIterativeWrite,
                                                 FileStoreTIFF,
                                                 FileStorePluginBase,
                                                 )
from ophyd import (Device, Component as Cpt, AreaDetector, TIFFPlugin,
                   HDF5Plugin)
from ophyd import (EpicsSignal, EpicsSignalRO)
from ophyd.areadetector import (EpicsSignalWithRBV as SignalWithRBV, CamBase)
from .utils import makedirs
from .trigger_mixins import HxnModalTrigger


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


class TimepixDetector(HxnModalTrigger, AreaDetector):
    _html_docs = []
    cam = Cpt(TimepixDetectorCam, 'cam1:',
              read_attrs=[],
              configuration_attrs=['tpx_corrections_dir', 'tpx_dac',
                                   'tpx_dac_file', 'tpx_dev_ip', 'tpx_hw_file',
                                   'tpx_system_id', 'tpx_pix_config_file',
                                   ])

    def mode_internal(self):
        super().mode_internal()

        count_time = self.modal_settings.count_time.get()
        self.cam.stage_sigs[self.cam.acquire_time] = count_time
        self.cam.stage_sigs[self.cam.acquire_period] = count_time + 0.005

        self.stage_sigs.move_to_end(self.cam.acquire)

    def mode_external(self):
        raise RuntimeError('Timepix external triggering not supported '
                           'reliably')


class TimepixTiffPlugin(TIFFPlugin, FileStoreTIFF, FileStoreIterativeWrite):
    def make_filename(self):
        fn, rp, write_path = super().make_filename()
        if self.parent.make_directories.get():
            makedirs(write_path)
        return fn, rp, write_path


class TimepixFileStoreHDF5(FileStorePluginBase, FileStoreIterativeWrite):
    _spec = 'TPX_HDF5'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs.update([(self.file_template, '%s%s_%6.6d.h5'),
                                (self.file_write_mode, 'Stream'),
                                (self.compression, 'zlib'),
                                (self.capture, 1)
                                ])

    def stage(self):
        super().stage()
        res_kwargs = {'frame_per_point': 1}
        logger.debug("Inserting resource with filename %s", self._fn)
        self._resource = fsapi.insert_resource(self._spec, self._fn,
                                               res_kwargs)


class HDF5PluginWithFileStore(HDF5Plugin, TimepixFileStoreHDF5):
    def make_filename(self):
        fn, rp, write_path = super().make_filename()
        if self.parent.make_directories.get():
            makedirs(write_path)
        return fn, rp, write_path

    def stage(self):
        total_points = self.parent.total_points.get()
        self.stage_sigs[self.num_capture] = total_points

        # ensure that setting capture is the last thing that's done
        self.stage_sigs.move_to_end(self.capture)
        super().stage()


class HxnTimepixDetector(TimepixDetector):
    hdf5 = Cpt(HDF5PluginWithFileStore, 'HDF1:',
               read_attrs=[],
               configuration_attrs=[],
               write_path_template='/data/%Y/%m/%d/')

    # tiff1 = Cpt(TimepixTiffPlugin, 'TIFF1:',
    #             read_attrs=[],
    #             configuration_attrs=[],
    #             write_path_template='/data/%Y/%m/%d/')

    def __init__(self, prefix, configuration_attrs=None, **kwargs):
        if configuration_attrs is None:
            configuration_attrs = ['cam', 'hdf5']
        super().__init__(prefix, configuration_attrs=configuration_attrs,
                         **kwargs)

        # signal aliases?
        self.total_points = self.modal_settings.total_points
        self.make_directories = self.modal_settings.make_directories
