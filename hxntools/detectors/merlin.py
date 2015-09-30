from __future__ import print_function
import logging

from ophyd.controls.areadetector.detectors import AreaDetector
from ophyd.controls.area_detector import AreaDetectorFSIterativeWrite
from .utils import makedirs

import filestore.api as fs


logger = logging.getLogger(__name__)


class MerlinFileStore(AreaDetectorFSIterativeWrite):
    def __init__(self, det, basename, **kwargs):
        super(MerlinFileStore, self).__init__(basename, cam='cam1:',
                                              **kwargs)
        self._det = det
        self._file_plugin = det.tiff1
        self.file_template = '%s%s_%6.6d.tiff'
        self._file_template = self._file_plugin.file_template

        # NOTE: hack to get parent classes to work...
        # NOTE: areadetector array sizes were rearranged to mirror numpy indexing
        #       so they differ from what AreaDetectorFSIterativeWrite expects
        self._arraysize0 = self._file_plugin.array_size.signals[1]
        self._arraysize1 = self._file_plugin.array_size.signals[0]
        self._external_triggering = False

    def _insert_fs_resource(self):
        return fs.insert_resource('AD_TIFF', self._store_file_path,
                                  {'template': self._file_template.value,
                                   'filename': self._filename,
                                   'frame_per_point': 1})

    def configure(self, *args, **kwargs):
        det = self._det

        plugin = self._file_plugin

        super(MerlinFileStore, self).configure(*args, **kwargs)
        # self._image_mode.put(0, wait=True)
        plugin.blocking_callbacks.put(1)
        plugin.file_template.put(self.file_template, wait=True)
        self._make_filename()
        plugin.file_path.put(self._ioc_file_path, wait=True)
        plugin.file_name.put(self._filename, wait=True)
        plugin.file_number.put(0)

        det.array_callbacks.put('Enable')

        if self._external_triggering:
            det.num_images.put(self._total_points)
            det.image_mode.put('Multiple')
            det.trigger_mode.put('External')
            # NOTE: these values specify a debounce time for external
            #       triggering so they should be set to < 0.5 the expected
            #       exposure time
            det.acquire_time.put(0.005)
            det.acquire_period.put(0.006)
        else:
            det.num_images.put(1)
            det.image_mode.put('Single')
            det.trigger_mode.put('Internal')

        plugin.auto_increment.put(1)
        plugin.auto_save.put(1)
        plugin.num_capture.put(self._total_points)
        plugin.file_write_mode.put(2)
        plugin.enable.put(1)
        plugin.capture.put(1)

        # print('** Please ensure Merlin is in external triggering (LVDS) '
        #       'mode **', file=sys.stderr)
        # # NOTE: this is not supported by the ascii protocol (and hence the
        # #       EPICS IOC) for some reason
        # switching timepix TTL to this for now
        self._filestore_res = self._insert_fs_resource()

        if self._external_triggering:
            det.acquire.put(1, wait=False)

    def deconfigure(self, *args, **kwargs):
        super(MerlinFileStore, self).deconfigure(*args, **kwargs)

        self._total_points = None
        self._det.tiff1.capture.put(0)

    def _make_filename(self, **kwargs):
        super(MerlinFileStore, self)._make_filename(**kwargs)

        makedirs(self._store_file_path)

    def set(self, total_points=0, external_trig=False, **kwargs):
        self._total_points = total_points
        self._external_triggering = bool(external_trig)


class MerlinDetector(AreaDetector):
    _html_docs = []

    def __init__(self, prefix, file_path='', ioc_file_path='', **kwargs):
        AreaDetector.__init__(self, prefix, **kwargs)

        self.filestore = MerlinFileStore(self, self._base_prefix,
                                         stats=[], shutter=None,
                                         file_path=file_path,
                                         ioc_file_path=ioc_file_path,
                                         name=self.name)
