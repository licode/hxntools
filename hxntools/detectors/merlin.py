from __future__ import print_function
import logging

from ophyd import (AreaDetector, CamBase, TIFFPlugin,
                   Component as Cpt
                   )
from ophyd.areadetector.filestore_mixins import (FileStoreIterativeWrite,
                                                 FileStoreTIFF)

from .utils import makedirs
from .trigger_mixins import (HxnModalTrigger, FileStoreBulkReadable)

import filestore.api as fs


logger = logging.getLogger(__name__)


#     def configure(self, state=None):
#         super(MerlinFileStore, self).configure(state=state)
#         ext_trig = (self._master is not None or self._external_trig)
#
#         plugin.blocking_callbacks.put(1)   # <-- not set, unsure if necessary
#         self._make_filename()  # <-- have to makedirs with right perms
#
#         plugin.num_capture.put(self._total_points)  # <-- set to 0
#         plugin.file_write_mode.put(2)  # <-- 'stream' here, 'single' on mixin


class MerlinTIFFPlugin(FileStoreTIFF, FileStoreBulkReadable, TIFFPlugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cam = self.parent.cam

    def mode_internal(self, scan_type=None):
        # super().mode_internal(scan_type=scan_type) # <- no super implementation
        logger.info('%s internal triggering (scan_type=%s)', self.name,
                    scan_type)

        remove_sigs = [self.cam.acquire_time,
                       self.cam.acquire_period]
        for sig in remove_sigs:
            try:
                del self.stage_sigs[sig]
            except KeyError:
                pass

    def mode_external(self, scan_type=None):
        # super().mode_external(scan_type=scan_type) # <- no super implementation
        logger.info('%s external triggering (scan_type=%s)', self.name,
                    scan_type)

        # NOTE: these values specify a debounce time for external
        #       triggering so they should be set to < 0.5 the expected
        #       exposure time
        self.stage_sigs[self.cam.acquire_time] = 0.005
        self.stage_sigs[self.cam.acquire_period] = 0.006


class MerlinDetectorCam(CamBase):
    pass


class MerlinDetector(AreaDetector):
    cam = Cpt(MerlinDetectorCam, 'cam1:')

    def __init__(self, prefix, **kwargs):
        super().__init__(prefix, **kwargs)


class HxnMerlinDetector(HxnModalTrigger, MerlinDetector):
    tiff1 = Cpt(MerlinTIFFPlugin, 'TIFF1:',
                write_path_template='/data/%Y/%m/%d/')
