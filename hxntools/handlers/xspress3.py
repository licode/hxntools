from __future__ import print_function

import h5py
import numpy as np

import filestore.api as fs_api
from filestore.handlers import HandlerBase


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

    @property
    def dataset(self):
        return self._dataset

    def __call__(self, frame=None, channel=None):
        # Don't read out the dataset until it is requested for the first time.
        if not self._dataset:
            self._dataset = self._file[self._key]

        return self._dataset[frame, channel - 1, :].squeeze()

    def get_roi(self, roi_info, frame=None, max_points=None):
        if not self._dataset:
            self._dataset = self._file[self._key]

        chan = roi_info.chan
        bin_low = roi_info.bin_low
        bin_high = roi_info.bin_high

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
