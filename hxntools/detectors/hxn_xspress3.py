# Since the hxntools.detectors.xspress3 module is now shared with srx, breaking
# out the truly hxn-specific stuff here
from collections import OrderedDict
import uuid
import itertools
import logging
import time

from ophyd import (Component as Cpt, Signal)
from ophyd.status import DeviceStatus
from ophyd.device import (BlueskyInterface, Staged)
from ophyd.utils import set_and_wait

from filestore.api import bulk_insert_datum
from .xspress3 import (XspressTrigger, Xspress3Detector, Xspress3FileStore)
from .trigger_mixins import HxnModalBase


logger = logging.getLogger(__name__)


class HxnXspressTrigger(HxnModalBase, BlueskyInterface):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._status = None
        self._acquisition_signal = self.settings.acquire
        self._abs_trigger_count = 0

    def unstage(self):
        ret = super().unstage()
        try:
            self._acquisition_signal.clear_sub(self._acquire_changed)
        except KeyError:
            pass

        return ret

    def _acquire_changed(self, value=None, old_value=None, **kwargs):
        "This is called when the 'acquire' signal changes."
        if self._status is None:
            return
        if (old_value == 1) and (value == 0):
            # Negative-going edge means an acquisition just finished.
            self._status._finished()

    def mode_internal(self):
        self._abs_trigger_count = 0
        self.stage_sigs[self.external_trig] = False
        self.stage_sigs[self.settings.acquire_time] = self.count_time.get()
        self._acquisition_signal.subscribe(self._acquire_changed)

    def mode_external(self):
        ms = self.mode_settings
        # NOTE: these are used in Xspress3Filestore.stage
        self.stage_sigs[self.external_trig] = True
        self.stage_sigs[self.total_points] = ms.total_points.get()
        self.stage_sigs[self.spectra_per_point] = 1
        self.stage_sigs[self.settings.acquire_time] = 0.001

        # NOTE: these are taken care of in Xspress3Filestore
        # self.stage_sigs[self.settings.trigger_mode] = 'TTL Veto Only'
        # self.stage_sigs[self.settings.num_images] = total_capture

    def _dispatch_channels(self, trigger_time):
        self._abs_trigger_count += 1
        channels = self._channels.values()
        for sn in self.read_attrs:
            ch = getattr(self, sn)
            if ch in channels:
                self.dispatch(ch.name, trigger_time)

    def trigger_internal(self):
        if self._staged != Staged.yes:
            raise RuntimeError("not staged")
        self._status = DeviceStatus(self)
        self.settings.erase.put(1)
        self._acquisition_signal.put(1, wait=False)
        self._dispatch_channels(trigger_time=time.time())
        return self._status

    def trigger_external(self):
        if self._staged != Staged.yes:
            raise RuntimeError("not staged")

        self._status = DeviceStatus(self)
        self._status._finished()
        if self.mode_settings.scan_type.get() != 'fly':
            self._dispatch_channels(trigger_time=time.time())
            # fly-scans take care of dispatching on their own

        return self._status

    def stage(self):
        staged = super().stage()
        mode = self.mode_settings.mode.get()
        if mode == 'external':
            # In external triggering mode, the devices is only triggered once
            # at stage
            self.settings.erase.put(1, wait=True)
            self._acquisition_signal.put(1, wait=False)
        return staged


class HxnXspress3DetectorBase(HxnXspressTrigger, Xspress3Detector):
    flyer_timestamps = Cpt(Signal)

    @property
    def hdf5_filename(self):
        return self.hdf5._fn

    def describe_collect(self):
        desc = Xspress3FileStore.describe(self.hdf5)

        for roi in self.enabled_rois:
            desc[roi.name] = dict(source='FILE:TBD', shape=[], dtype='number')

        return [desc]

    def bulk_read(self, timestamps=None):
        # TODO not compatible with collect() just yet due to the values
        #      returned
        fs_res = self.hdf5._filestore_res
        if timestamps is None:
            timestamps = self.flyer_timestamps.get()

        if timestamps is None:
            raise ValueError('Timestamps must be set first')

        channels = self.channels
        ch_uids = {ch: [str(uuid.uuid4()) for ts in timestamps]
                   for ch in channels}

        count = len(timestamps)
        if count == 0:
            return {}

        def get_datum_args():
            for ch in channels:
                for seq_num in range(count):
                    yield {'frame': seq_num,
                           'channel': ch}

        uids = [ch_uids[ch] for ch in channels]
        bulk_insert_datum(fs_res, itertools.chain(*uids),
                          get_datum_args())
        return OrderedDict((self.hdf5.mds_keys[ch], ch_uids[ch])
                           for ch in channels)

    def fly_collect_rois(self):
        # Purposefully try reading the hdf5 file *AFTER* inserting the spectra
        # entries to filestore:
        hdf5 = self.hdf5._fn
        for name, roi_data in self.read_hdf5(hdf5):
            yield (name, roi_data)

    def stop(self):
        super().stop()

        logger.info('Ensuring detector %r capture stopped...',
                    self.name)
        set_and_wait(self.settings.acquire, 0)
        self.hdf5.stop()
        logger.info('... detector %r ok', self.name)
