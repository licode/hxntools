# Since the hxntools.detectors.xspress3 module is now shared with srx, breaking
# out the truly hxn-specific stuff here
from collections import OrderedDict
import uuid
import itertools
import logging

from ophyd import (Component as Cpt, Signal)
from ophyd.utils import set_and_wait

from filestore.api import bulk_insert_datum
from .xspress3 import (XspressTrigger, Xspress3Detector, Xspress3FileStore,
                       )


logger = logging.getLogger(__name__)


class HxnXspress3DetectorBase(XspressTrigger, Xspress3Detector):
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
        set_and_wait(self.hdf5.capture, 0)
        logger.info('... detector %r ok', self.name)
