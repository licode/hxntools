from __future__ import print_function
import sys
import logging
import time

from ophyd.controls.areadetector.detectors import AreaDetector
from ophyd.controls.area_detector import AreaDetectorFileStoreTIFF
from .utils import (makedirs, get_total_scan_points)


logger = logging.getLogger(__name__)


class MerlinFileStore(AreaDetectorFileStoreTIFF):
    def __init__(self, det, basename, **kwargs):
        super(MerlinFileStore, self).__init__(basename, cam='cam1:',
                                              **kwargs)
        self._det = det

        if not det.tiff1.file_template.value:
            det.tiff1.file_template.put('%s%s_%6.6d.tiff')

    def _extra_AD_configuration(self):
        det = self._det

        num_points = get_total_scan_points(self._num_scan_points)

        det.array_callbacks.put('Enable')
        det.num_images.put(num_points)
        det.image_mode.put('Multiple')
        det.trigger_mode.put('External')

        # NOTE: these values appear to specify the minima for the
        #       external triggering
        det.acquire_time.put(0.005)
        det.acquire_period.put(0.006)

        tiff1 = det.tiff1
        tiff1.auto_increment.put(1)
        tiff1.auto_save.put(1)
        tiff1.num_capture.put(num_points)
        tiff1.file_write_mode.put(2)
        tiff1.enable.put(1)
        tiff1.capture.put(1)

        det.acquire.put(1)

        # print('** Please ensure Merlin is in external triggering (LVDS) '
        #       'mode **', file=sys.stderr)
        # # NOTE: this is not supported by the ascii protocol (and hence the
        # #       EPICS IOC) for some reason
        # switching timepix TTL to this for now
        # time.sleep(2)

    def deconfigure(self, *args, **kwargs):
        super(MerlinFileStore, self).deconfigure(*args, **kwargs)

        self.set_scan(None)
        self._det.tiff1.capture.put(0)

    def _make_filename(self, **kwargs):
        super(MerlinFileStore, self)._make_filename(**kwargs)

        makedirs(self._store_file_path)

    def set_scan(self, scan):
        self._scan = scan

        if scan is None:
            return

        self._num_scan_points = scan.npts + 1


class MerlinDetector(AreaDetector):
    _html_docs = []

    def __init__(self, prefix, file_path='', ioc_file_path='', **kwargs):
        AreaDetector.__init__(self, prefix, **kwargs)

        self.filestore = MerlinFileStore(self, self._base_prefix,
                                         stats=[], shutter=None,
                                         file_path=file_path,
                                         ioc_file_path=ioc_file_path,
                                         name=self.name)
