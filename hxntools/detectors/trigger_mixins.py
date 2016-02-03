import time as ttime
import logging
import itertools

from ophyd.device import (DeviceStatus, BlueskyInterface, Staged)
from ophyd.utils import set_and_wait

logger = logging.getLogger(__name__)


class TriggerBase(BlueskyInterface):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.stage_sigs.update([(self.cam.acquire, 0),  # If acquiring, stop.
                                (self.cam.image_mode, 'Multiple'),  # 'Multiple' mode
                                ])

        self._status = None
        self._acquisition_signal = self.cam.acquire


class HxnModalTrigger(BlueSkyInterface):
    def __init__(self, *args, image_name=None, **kwargs):
        super().__init__(*args, **kwargs)
        if image_name is None:
            image_name = '_'.join([self.name, 'image'])
        self._image_name = image_name

    def set(self, *, total_points=0, external_trig=False, master=None):
        self._master = master
        self._total_points = total_points
        self._external_trig = bool(external_trig)

        if self._master is not None or self._external_trig:
            self.mode_setup('external')
        else:
            self.mode_setup('internal')

    def mode_setup(self, mode):
        attr = 'setup_{}'.format(mode)
        if hasattr(self, attr):
            mode_setup_method = getattr(self, attr)
            mode_setup_method()

    def setup_internal(self):
        cam = self.parent.cam
        self.stage_sigs[cam.num_images] = 1
        self.stage_sigs[cam.image_mode] = 'Single'
        self.stage_sigs[cam.trigger_mode] = 'Internal'
        if cam.acquire in self.stage_sigs:
            del self.stage_sigs[cam.acquire]

    def setup_external(self):
        if self._total_points is None:
            raise RuntimeError('set was not called on this detector')

        cam = self.parent.cam
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
        '''Trigger one acquisition.'''
        if self._external_trig:
            self.trigger_external()
        else:
            self.trigger_internal()

    def trigger_internal(self):
        if self._staged != Staged.yes:
            raise RuntimeError("This detector is not ready to trigger."
                               "Call the stage() method before triggering.")

        self._status = DeviceStatus(self)
        self._acquisition_signal.put(1, wait=False)
        self.dispatch(self._image_name, ttime.time())
        return self._status

    def trigger_external(self):
        pass

    def _acquire_changed(self, value=None, old_value=None, **kwargs):
        '''This is called when the 'acquire' signal changes.'''
        if self._status is None:
            return
        if (old_value == 1) and (value == 0):
            # Negative-going edge means an acquisition just finished.
            self._status._finished()

    def bulk_read(self, timestamps):
        # TODO update
        uids = list(str(uuid.uuid4()) for ts in timestamps)
        datum_args = (dict(point_number=i) for i in range(len(uids)))
        bulk_insert_datum(self._filestore_res, uids, datum_args)
        return {self._det.name: uids}
