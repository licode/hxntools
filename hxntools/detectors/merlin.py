from __future__ import print_function
import logging
import uuid

from filestore.commands import bulk_insert_datum
from ophyd import (AreaDetector, TIFFPlugin)
from .utils import makedirs
from .trigger_mixins import HxnModalTrigger

import filestore.api as fs


logger = logging.getLogger(__name__)


#     def describe(self):
#         size = (self._arraysize1.value,
#                 self._arraysize0.value)
#
#         return {self._det.name: {'external': 'FILESTORE:',
#                                  'source': 'PV:{}'.format(self._basename),
#                                  'shape': size, 'dtype': 'array'}
#                 }
#
#     def configure(self, state=None):
#         super(MerlinFileStore, self).configure(state=state)
#         ext_trig = (self._master is not None or self._external_trig)
#
#         plugin.blocking_callbacks.put(1)   # <-- not set, unsure if necessary
#         self._make_filename()  # <-- have to makedirs with right perms
#
#         plugin.num_capture.put(self._total_points)  # <-- set to 0
#         plugin.file_write_mode.put(2)  # <-- 'stream' here, 'single' on mixin


class MerlinTIFFPlugin(FileStoreIterativeWrite, TIFFPlugin):
    def setup_external(self):
        # NOTE: these values specify a debounce time for external
        #       triggering so they should be set to < 0.5 the expected
        #       exposure time
        self.stage_sigs[cam.acquire_time] = 0.005
        self.stage_sigs[cam.acquire_period] = 0.006


class MerlinDetector(AreaDetector):
    _html_docs = []
    cam = Cpt(MerlinCam, 'cam1:')

    def __init__(self, prefix, **kwargs):
        super().__init__(prefix, **kwargs)


class HxnMerlinDetector(HxnModalTrigger, MerlinDetector):
    tiff1 = Cpt(MerlinTIFFPlugin, 'TIFF1:', cam_name='cam',
                write_path_template='/data/%Y/%m/%d/')
