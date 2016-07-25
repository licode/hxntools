import logging

import filestore.api as fsapi
from ophyd.areadetector.filestore_mixins import (FileStoreIterativeWrite,
                                                 FileStoreTIFF,
                                                 FileStorePluginBase,
                                                 )
from ophyd import (Device, Component as Cpt, AreaDetector, TIFFPlugin,
                   HDF5Plugin, StatsPlugin, ProcessPlugin, ROIPlugin,
                   TransformPlugin)
from ophyd import (EpicsSignal, EpicsSignalRO)
from ophyd.areadetector import (EpicsSignalWithRBV as SignalWithRBV, CamBase)
from .utils import makedirs
from .trigger_mixins import (HxnModalTrigger, FileStoreBulkReadable)


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

        count_time = self.count_time.get()
        if count_time is not None:
            self.cam.stage_sigs[self.cam.acquire_time] = count_time
            self.cam.stage_sigs[self.cam.acquire_period] = count_time + 0.020

    def mode_external(self):
        raise RuntimeError('Timepix external triggering not supported '
                           'reliably')


class TimepixTiffPlugin(TIFFPlugin, FileStoreBulkReadable, FileStoreTIFF,
                        Device):
    def mode_external(self):
        total_points = self.parent.mode_settings.total_points.get()
        self.stage_sigs[self.num_capture] = total_points

    def get_frames_per_point(self):
        mode = self.parent.mode_settings.mode.get()
        if mode == 'external':
            return 1
        else:
            return self.parent.cam.num_images.get()


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
        staged = super().stage()
        res_kwargs = {'frame_per_point': 1}
        logger.debug("Inserting resource with filename %s", self._fn)
        self._resource = fsapi.insert_resource(self._spec, self._fn,
                                               res_kwargs)
        return staged

    def make_filename(self):
        fn, read_path, write_path = super().make_filename()
        if self.parent.make_directories.get():
            makedirs(read_path)
        return fn, read_path, write_path


class HDF5PluginWithFileStore(HDF5Plugin, TimepixFileStoreHDF5):
    def stage(self):
        total_points = self.parent.total_points.get()
        self.stage_sigs[self.num_capture] = total_points

        # ensure that setting capture is the last thing that's done
        self.stage_sigs.move_to_end(self.capture)
        return super().stage()


class HxnTimepixDetector(TimepixDetector):
    hdf5 = Cpt(HDF5PluginWithFileStore, 'HDF1:',
               read_attrs=[],
               configuration_attrs=[],
               write_path_template='/data/%Y/%m/%d/')

    proc1 = Cpt(ProcessPlugin, 'Proc1:')
    stats1 = Cpt(StatsPlugin, 'Stats1:')
    stats2 = Cpt(StatsPlugin, 'Stats2:')
    stats3 = Cpt(StatsPlugin, 'Stats3:')
    stats4 = Cpt(StatsPlugin, 'Stats4:')
    stats5 = Cpt(StatsPlugin, 'Stats5:')
    transform1 = Cpt(TransformPlugin, 'Trans1:')
    roi1 = Cpt(ROIPlugin, 'ROI1:')
    roi2 = Cpt(ROIPlugin, 'ROI2:')
    roi3 = Cpt(ROIPlugin, 'ROI3:')
    roi4 = Cpt(ROIPlugin, 'ROI4:')

    # tiff1 = Cpt(TimepixTiffPlugin, 'TIFF1:',
    #             read_attrs=[],
    #             configuration_attrs=[],
    #             write_path_template='/data/%Y/%m/%d/')

    def __init__(self, prefix, *, read_attrs=None, configuration_attrs=None,
                 **kwargs):
        if read_attrs is None:
            read_attrs = ['cam', 'hdf5']
        if configuration_attrs is None:
            configuration_attrs = ['cam', 'hdf5']

        if 'hdf5' not in read_attrs:
            # ensure that hdf5 is still added, or data acquisition will fail
            read_attrs = list(read_attrs) + ['hdf5']

        super().__init__(prefix, configuration_attrs=configuration_attrs,
                         read_attrs=read_attrs, **kwargs)

        # signal aliases?
        self.total_points = self.mode_settings.total_points
        self.make_directories = self.mode_settings.make_directories

    def mode_internal(self):
        super().mode_internal()

        num_exposures = self.cam.num_exposures.get()
        cam = self.cam
        proc1 = self.proc1
        hdf5 = self.hdf5

        if num_exposures <= 1:
            cam.stage_sigs[cam.image_mode] = 'Single'
            hdf5.stage_sigs[hdf5.nd_array_port] = cam.port_name.get()
        else:
            # multiple exposures isn't supported by the timepix driver :(
            # use the process plugin to sum the images
            cam.stage_sigs[cam.image_mode] = 'Multiple'
            cam.stage_sigs[cam.num_images] = num_exposures
            hdf5.stage_sigs[hdf5.nd_array_port] = proc1.port_name.get()
            proc1.stage_sigs[proc1.num_filter] = num_exposures
            proc1.stage_sigs[proc1.reset_filter] = 'Yes'
            proc1.stage_sigs[proc1.auto_reset_filter] = 'Yes'
            proc1.stage_sigs[proc1.enable_filter] = 'Enable'
            proc1.stage_sigs[proc1.filter_type] = 'Sum'
            proc1.stage_sigs[proc1.filter_callbacks] = 'Array N only'

        proc1.stage_sigs[proc1.blocking_callbacks] = 'Yes'
        hdf5.stage_sigs[hdf5.blocking_callbacks] = 'Yes'
