import os
import time as ttime
import logging
# import itertools
import uuid

from ophyd.device import (DeviceStatus, BlueskyInterface, Staged,
                          Component as Cpt, Device)
from ophyd import (Signal, )
from ophyd.areadetector.filestore_mixins import FileStoreIterativeWrite

from filestore.api import bulk_insert_datum
from .utils import (makedirs, ordered_dict_move_to_beginning)

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
    count_time = Cpt(Signal, value=1.0,
                     doc='Exposure/count time, as specified by bluesky')
    mode = Cpt(Signal, value='internal',
               doc='Triggering mode (external/external)')
    scan_type = Cpt(Signal, value='?',
                    doc='Scan type (?)')
    make_directories = Cpt(Signal, value=True,
                           doc='Make directories on the DAQ side')
    total_points = Cpt(Signal, value=2,
                       doc='The total number of points to acquire overall')
    triggers = Cpt(Signal, value=None,
                   doc='Detector instances which this one triggers')


class HxnModalBase(Device):
    mode_settings = Cpt(HxnModalSettings, '')

    @property
    def count_time(self):
        return self.mode_settings.count_time.get()

    @count_time.setter
    def count_time(self, value):
        if value is None:
            return

        self.mode_settings.count_time.put(value)

    def mode_setup(self, mode):
        devices = [self] + [getattr(self, attr) for attr in self._sub_devices]
        attr = 'mode_{}'.format(mode)
        for dev in devices:
            if hasattr(dev, attr):
                mode_setup_method = getattr(dev, attr)
                mode_setup_method()

    def mode_internal(self):
        logger.info('%s internal triggering %s', self.name,
                    self.mode_settings.get())

    def mode_external(self):
        logger.info('%s external triggering %s', self.name,
                    self.mode_settings.get())

    @property
    def mode(self):
        return self.mode_settings.mode.get()

    def stage(self):
        self.mode_setup(self.mode)
        super().stage()


class HxnModalTrigger(HxnModalBase, TriggerBase):
    mode_settings = Cpt(HxnModalSettings, '')

    def __init__(self, *args, image_name=None, **kwargs):
        super().__init__(*args, **kwargs)
        if image_name is None:
            image_name = '_'.join([self.name, 'image'])
        self._image_name = image_name

    def mode_internal(self):
        scan_type = self.mode_settings.scan_type.get()
        total_points = self.mode_settings.total_points.get()
        logger.info('%s internal triggering (scan_type=%s; total_points=%d)',
                    self.name, scan_type, total_points)
        cam = self.cam

        self.stage_sigs[cam.acquire] = 0
        ordered_dict_move_to_beginning(self.stage_sigs, cam.acquire)

        self.stage_sigs[cam.num_images] = 1
        self.stage_sigs[cam.image_mode] = 'Single'
        self.stage_sigs[cam.trigger_mode] = 'Internal'

    def mode_external(self):
        scan_type = self.mode_settings.scan_type.get()
        total_points = self.mode_settings.total_points.get()
        logger.info('%s external triggering (scan_type=%s; total_points=%d)',
                    self.name, scan_type, total_points)

        cam = self.cam
        self.stage_sigs[cam.num_images] = total_points
        self.stage_sigs[cam.image_mode] = 'Multiple'
        self.stage_sigs[cam.trigger_mode] = 'External'

        self.stage_sigs[cam.acquire] = 1
        self.stage_sigs.move_to_end(cam.acquire)

    def stage(self):
        self._acquisition_signal.subscribe(self._acquire_changed)
        super().stage()

    def unstage(self):
        try:
            super().unstage()
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
        self._status = DeviceStatus(self)
        self._status._finished(success=True)
        return self._status

    def trigger(self):
        mode = self.mode_settings.mode.get()
        mode_setup_method = getattr(self, 'trigger_{}'.format(mode))
        return mode_setup_method()

    def _acquire_changed(self, value=None, old_value=None, **kwargs):
        '''This is called when the 'acquire' signal changes.'''
        if self._status is None:
            return
        if (old_value == 1) and (value == 0):
            # Negative-going edge means an acquisition just finished.
            self._status._finished()


class FileStoreBulkReadable(FileStoreIterativeWrite):
    def __init__(self, *args, **kwargs):
        self._write_path_template = None
        super().__init__(*args, **kwargs)

    def make_filename(self):
        fn, read_path, write_path = super().make_filename()

        # tag on a portion of the hash to reduce the number of files in one
        # directory
        hash_portion = fn[:5]
        read_path = os.path.join(read_path, hash_portion, '')
        write_path = os.path.join(write_path, hash_portion, '')

        makedirs(read_path, mode=0o777)
        return fn, read_path, write_path

    def bulk_read(self, timestamps):
        # TODO update
        uids = list(str(uuid.uuid4()) for ts in timestamps)
        datum_args = (dict(point_number=i) for i in range(len(uids)))
        bulk_insert_datum(self._resource, uids, datum_args)
        return {self.parent._image_name: uids}
