from __future__ import print_function

import logging

# imort XRF_DATA_KEY for back-compat
from filestore.handlers import (Xspress3HDF5Handler,
                                XS3_XRF_DATA_KEY as XRF_DATA_KEY)


logger = logging.getLogger(__name__)

FMT_ROI_KEY = 'entry/instrument/detector/NDAttributes/CHAN{}ROI{}'


def register():
    import filestore.api as fs_api
    fs_api.register_handler(Xspress3HDF5Handler.HANDLER_NAME,
                            Xspress3HDF5Handler)
