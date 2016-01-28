from __future__ import print_function

import h5py
import numpy as np
import logging

import filestore.api as fs_api
from filestore.handlers import HandlerBase


logger = logging.getLogger(__name__)

FMT_ROI_KEY = 'entry/instrument/detector/NDAttributes/CHAN{}ROI{}'
XRF_DATA_KEY = 'entry/instrument/detector/data'


class Xspress3HDF5Handler(HandlerBase):
    specs = {'XSP3'} | HandlerBase.specs
    HANDLER_NAME = 'XSP3'

    def __init__(self, filename, key=XRF_DATA_KEY):
        if isinstance(filename, h5py.File):
            self._file = filename
            self._filename = self._file.filename
        else:
            self._filename = filename
            self._file = None
        self._key = key
        self._dataset = None

        self.open()

    def open(self):
        if self._file:
            return

        self._file = h5py.File(self._filename, 'r')

    def close(self):
        super(Xspress3HDF5Handler, self).close()
        self._file.close()
        self._file = None
        self._dataset = None

    @property
    def dataset(self):
        return self._dataset

    def _get_dataset(self):
        if self._dataset is not None:
            return

        hdf_dataset = self._file[self._key]
        try:
            self._dataset = np.asarray(hdf_dataset)
        except MemoryError as ex:
            logger.warning('Unable to load the full dataset into memory',
                           exc_info=ex)
            self._dataset = hdf_dataset

    def __del__(self):
        self.close()

    def __call__(self, frame=None, channel=None):
        # Don't read out the dataset until it is requested for the first time.
        self._get_dataset()
        return self._dataset[frame, channel - 1, :].squeeze()

    def get_roi(self, chan, bin_low, bin_high, *, frame=None, max_points=None):
        self._get_dataset()

        roi = np.sum(self._dataset[:, chan - 1, bin_low:bin_high], axis=1)
        if max_points is not None:
            roi = roi[:max_points]

            if len(roi) < max_points:
                roi = np.pad(roi, ((0, max_points - len(roi)), ), 'constant')

        if frame is not None:
            roi = roi[frame, :]

        return roi

    def __repr__(self):
        return '{0.__class__.__name__}(filename={0._filename!r})'.format(self)


fs_api.register_handler(Xspress3HDF5Handler.HANDLER_NAME,
                        Xspress3HDF5Handler)
