from __future__ import print_function
import logging

from ophyd import (AreaDetector, CamBase, TIFFPlugin, Component as Cpt,
                   HDF5Plugin)
from ophyd.areadetector.filestore_mixins import (
    FileStoreIterativeWrite, FileStoreTIFF, FileStorePluginBase)

from .utils import (makedirs, make_filename_add_subdirectory)
from .trigger_mixins import (HxnModalTrigger, FileStoreBulkReadable)
import filestore.api as fsapi


logger = logging.getLogger(__name__)

# blocking_callbacks.put(1)   # <-- not set, unsure if necessary
# num_capture.put(self._total_points)  # <-- set to 0


class MerlinTiffPlugin(TIFFPlugin, FileStoreTIFF, FileStoreIterativeWrite):
    def make_filename(self):
        fn, read_path, write_path = super().make_filename()
        make_dirs = self.parent.make_directories.get()
        return make_filename_add_subdirectory(fn, read_path, write_path,
                                              make_directories=make_dirs)


class MerlinDetectorCam(CamBase):
    pass


class MerlinDetector(AreaDetector):
    cam = Cpt(MerlinDetectorCam, 'cam1:')

    def __init__(self, prefix, **kwargs):
        super().__init__(prefix, **kwargs)


class MerlinFileStoreHDF5(FileStorePluginBase, FileStoreIterativeWrite):
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

    def make_filename(self):
        fn, read_path, write_path = super().make_filename()
        if self.parent.make_directories.get():
            makedirs(read_path)
        return fn, read_path, write_path


class HDF5PluginWithFileStore(HDF5Plugin, MerlinFileStoreHDF5):
    def stage(self):
        total_points = self.parent.total_points.get()
        self.stage_sigs[self.num_capture] = total_points

        # ensure that setting capture is the last thing that's done
        self.stage_sigs.move_to_end(self.capture)
        super().stage()


class HxnMerlinDetector(HxnModalTrigger, MerlinDetector):
    hdf5 = Cpt(HDF5PluginWithFileStore, 'HDF1:',
               read_attrs=[],
               configuration_attrs=[],
               write_path_template='/data/%Y/%m/%d/')

    tiff1 = Cpt(MerlinTiffPlugin, 'TIFF1:',
                read_attrs=[],
                configuration_attrs=[],
                write_path_template='/data/%Y/%m/%d/')

    def mode_internal(self):
        logger.info('%s internal triggering (%s)', self.name,
                    self.mode_settings)
        self.stage_sigs[self.cam.acquire_time] = 0.005
        self.stage_sigs[self.cam.acquire_period] = 0.006

    def mode_external(self):
        logger.info('%s external triggering (%s)', self.name,
                    self.mode_settings)

        # NOTE: these values specify a debounce time for external triggering so
        #       they should be set to < 0.5 the expected exposure time
        self.stage_sigs[self.cam.acquire_time] = 0.005
        self.stage_sigs[self.cam.acquire_period] = 0.006
