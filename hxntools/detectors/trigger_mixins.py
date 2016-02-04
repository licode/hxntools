import time as ttime
import logging
import itertools
import uuid

from ophyd.device import (DeviceStatus, BlueskyInterface, Staged)
from ophyd.utils import set_and_wait
from ophyd.areadetector.filestore_mixins import FileStoreIterativeWrite

from filestore.commands import bulk_insert_datum

logger = logging.getLogger(__name__)


class TriggerBase(BlueskyInterface):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.stage_sigs.update([(self.cam.acquire, 0),  # If acquiring, stop.
                                (self.cam.image_mode, 'Multiple'),  # 'Multiple' mode
                                ])

        self._status = None
        self._acquisition_signal = self.cam.acquire


class HxnModalTrigger(TriggerBase):
    def __init__(self, *args, image_name=None, **kwargs):
        super().__init__(*args, **kwargs)
        if image_name is None:
            image_name = '_'.join([self.name, 'image'])
        self._image_name = image_name

    def set(self, *, total_points=0, external_trig=False, master=None,
            scan_type=None):
        self._master = master
        self._total_points = total_points
        self._external_trig = bool(external_trig)
        self._scan_type = scan_type

        if self._master is not None or self._external_trig:
            mode = 'external'
        else:
            mode = 'internal'

        self.mode_setup(mode, scan_type=scan_type)

    def mode_setup(self, mode, **kwargs):
        devices = [self] + [getattr(self, attr) for attr in self._sub_devices]
        attr = 'mode_{}'.format(mode)
        for dev in devices:
            if hasattr(dev, attr):
                mode_setup_method = getattr(dev, attr)
                mode_setup_method(**kwargs)

    def mode_internal(self, scan_type=None):
        logger.info('%s internal triggering (scan_type=%s)', self.name,
                    scan_type)
        cam = self.cam
        self.stage_sigs[cam.num_images] = 1
        self.stage_sigs[cam.image_mode] = 'Single'
        self.stage_sigs[cam.trigger_mode] = 'Internal'
        if cam.acquire in self.stage_sigs:
            del self.stage_sigs[cam.acquire]

    def mode_external(self, scan_type=None):
        logger.info('%s external triggering (scan_type=%s)', self.name,
                    scan_type)
        if self._total_points is None:
            raise RuntimeError('set was not called on this detector')

        cam = self.cam
        self.stage_sigs[cam.num_images] = self._total_points
        self.stage_sigs[cam.image_mode] = 'Multiple'
        self.stage_sigs[cam.trigger_mode] = 'External'
        self.stage_sigs[cam.acquire] = 1

    def stage(self):
        self._acquisition_signal.subscribe(self._acquire_changed)
        super().stage()

    def unstage(self):
        try:
            super().unstage()
        finally:
            self._acquisition_signal.clear_sub(self._acquire_changed)
            self._total_points = None
            self._master = None

    def trigger(self):
        if self._staged != Staged.yes:
            raise RuntimeError("This detector is not ready to trigger."
                               "Call the stage() method before triggering.")

        self._status = DeviceStatus(self)
        self._acquisition_signal.put(1, wait=False)
        self.dispatch(self._image_name, ttime.time())
        return self._status

    def _acquire_changed(self, value=None, old_value=None, **kwargs):
        '''This is called when the 'acquire' signal changes.'''
        if self._status is None:
            return
        if (old_value == 1) and (value == 0):
            # Negative-going edge means an acquisition just finished.
            self._status._finished()


class FileStoreBulkReadable(FileStoreIterativeWrite):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def bulk_read(self, timestamps):
        # TODO update
        uids = list(str(uuid.uuid4()) for ts in timestamps)
        datum_args = (dict(point_number=i) for i in range(len(uids)))
        bulk_insert_datum(self._resource, uids, datum_args)
        return {self.parent._image_name: uids}
