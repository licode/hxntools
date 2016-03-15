from .xspress3 import Xspress3HDF5Handler
from .timepix import TimepixHDF5Handler


def register():
    from .xspress3 import register
    register()
    from .timepix import register
    register()
