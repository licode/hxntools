import time as ttime
import logging

from ophyd.device import (DeviceStatus, BlueskyInterface, Staged,
                          Component as Cpt, Device)
from ophyd import (Signal, )
from ophyd.areadetector.filestore_mixins import FileStoreBulkWrite

from filestore.api import bulk_insert_datum
from .utils import (ordered_dict_move_to_beginning,
                    make_filename_add_subdirectory)

logger = logging.getLogger(__name__)


class TriggerBase(BlueskyInterface):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # If acquiring, stop.
        self.stage_sigs[self.cam.acquire] = 0
        self.stage_sigs[self.cam.image_mode] = 'Multiple'
        self._acquisition_signal = self.cam.acquire

        self._status = None


class HxnModalSettings(Device):
    mode = Cpt(Signal, value='internal',
               doc='Triggering mode (external/external)')
    scan_type = Cpt(Signal, value='step',
                    doc='Scan type (step/scaler)')
    make_directories = Cpt(Signal, value=True,
                           doc='Make directories on the DAQ side')
    total_points = Cpt(Signal, value=2,
                       doc='The total number of points to acquire overall')
    triggers = Cpt(Signal, value=None,
                   doc='Detector instances which this one triggers')


class HxnModalBase(Device):
    mode_settings = Cpt(HxnModalSettings, '')
    count_time = Cpt(Signal, value=1.0,
                     doc='Exposure/count time, as specified by bluesky')

    def mode_setup(self, mode):
        devices = [self] + [getattr(self, attr) for attr in self._sub_devices]
        attr = 'mode_{}'.format(mode)
        for dev in devices:
            if hasattr(dev, attr):
                mode_setup_method = getattr(dev, attr)
                mode_setup_method()

    def mode_internal(self):
        logger.debug('%s internal triggering %s', self.name,
                     self.mode_settings.get())

    def mode_external(self):
        logger.debug('%s external triggering %s', self.name,
                     self.mode_settings.get())

    @property
    def mode(self):
        return self.mode_settings.mode.get()

    def stage(self):
        if self._staged != Staged.yes:
            self.mode_setup(self.mode)

        return super().stage()


class HxnModalTrigger(HxnModalBase, TriggerBase):
    def __init__(self, *args, image_name=None, **kwargs):
        super().__init__(*args, **kwargs)
        if image_name is None:
            image_name = '_'.join([self.name, 'image'])
        self._image_name = image_name
        self._external_acquire_at_stage = True

    def stop(self):
        ret = super().stop()
        self._acquisition_signal.put(0, wait=True)
        return ret

    def mode_internal(self):
        super().mode_internal()

        cam = self.cam
        cam.stage_sigs[cam.acquire] = 0
        ordered_dict_move_to_beginning(cam.stage_sigs, cam.acquire)

        cam.stage_sigs[cam.num_images] = 1
        cam.stage_sigs[cam.image_mode] = 'Single'
        cam.stage_sigs[cam.trigger_mode] = 'Internal'

    def mode_external(self):
        super().mode_external()
        total_points = self.mode_settings.total_points.get()

        cam = self.cam
        cam.stage_sigs[cam.num_images] = total_points
        cam.stage_sigs[cam.image_mode] = 'Multiple'
        cam.stage_sigs[cam.trigger_mode] = 'External'

    def stage(self):
        self._acquisition_signal.subscribe(self._acquire_changed)
        staged = super().stage()

        # In external triggering mode, the devices is only triggered once at
        # stage
        mode = self.mode_settings.mode.get()
        if mode == 'external' and self._external_acquire_at_stage:
            self._acquisition_signal.put(1, wait=False)
        return staged

    def unstage(self):
        try:
            return super().unstage()
        finally:
            self._acquisition_signal.clear_sub(self._acquire_changed)

    def trigger_internal(self):
        if self._staged != Staged.yes:
            raise RuntimeError("This detector is not ready to trigger."
                               "Call the stage() method before triggering.")

        self._status = DeviceStatus(self)
        self._acquisition_signal.put(1, wait=False)
        self.dispatch(self._image_name, ttime.time())
        return self._status

    def trigger_external(self):
        if self._staged != Staged.yes:
            raise RuntimeError("This detector is not ready to trigger."
                               "Call the stage() method before triggering.")

        self._status = DeviceStatus(self)
        self._status._finished()
        # TODO this timestamp is inaccurate!
        self.dispatch(self._image_name, ttime.time())
        return self._status

    def trigger(self):
        mode = self.mode_settings.mode.get()
        mode_trigger = getattr(self, 'trigger_{}'.format(mode))
        return mode_trigger()

    def _acquire_changed(self, value=None, old_value=None, **kwargs):
        '''This is called when the 'acquire' signal changes.'''
        if self._status is None:
            return
        if (old_value == 1) and (value == 0):
            # Negative-going edge means an acquisition just finished.
            self._status._finished()


class FileStoreBulkReadable(FileStoreBulkWrite):
    def make_filename(self):
        fn, read_path, write_path = super().make_filename()
        make_dirs = self.parent.mode_settings.make_directories.get()
        return make_filename_add_subdirectory(fn, read_path, write_path,
                                              make_directories=make_dirs)

    def bulk_read(self, timestamps):
        image_name = self.image_name
        uids = [self.generate_datum(self.image_name, ts) for ts in timestamps]
        datum_args = [self._datum_kwargs_map[uid] for uid in uids]

        bulk_insert_datum(self._resource, uids, datum_args)

        # clear so unstage will not save the images twice:
        self._datum_uids.clear()
        self._datum_kwargs_map.clear()
        return {image_name: uids}

    @property
    def image_name(self):
        return self.parent._image_name
