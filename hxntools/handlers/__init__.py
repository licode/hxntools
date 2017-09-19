from __future__ import absolute_import

# imports to expose out to world
from .xspress3 import Xspress3HDF5Handler
from .timepix import TimepixHDF5Handler


def register(db):
    from .xspress3 import register
    register(db)
    from .timepix import register
    register(db)
