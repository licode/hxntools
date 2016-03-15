from filestore.handlers import HDF5DatasetSliceHandler


class TimepixHDF5Handler(HDF5DatasetSliceHandler):
    """
    Handler for the 'AD_HDF5' spec used by Area Detectors.
    In this spec, the key (i.e., HDF5 dataset path) is always
    '/entry/detector/data'.
    Parameters
    ----------
    filename : string
        path to HDF5 file
    frame_per_point : integer, optional
        number of frames to return as one datum, default 1
    """
    specs = {'AD_HDF5'} | HDF5DatasetSliceHandler.specs
    HANDLER_NAME = 'AD_HDF5'

    # TODO this is only different due to the hardcoded key being different?
    hardcoded_key = '/entry/instrument/detector/data'

    def __init__(self, filename, frame_per_point=1):
        super().__init__(filename=filename, key=self.hardcoded_key,
                         frame_per_point=frame_per_point)


def register():
    import filestore.api as fs_api
    fs_api.register_handler(TimepixHDF5Handler.HANDLER_NAME,
                            TimepixHDF5Handler, overwrite=True)
