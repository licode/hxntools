import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d, interp2d

from hxntools.scan_info import ScanInfo


def fly2d_grid(hdr, x_data=None, y_data=None, plot=False):
    '''Get ideal gridded points for a 2D flyscan'''
    hdr = hdr['start']
    try:
        nx, ny = hdr['dimensions']
    except ValueError:
        raise ValueError('Not a 2D flyscan (dimensions={})'
                         ''.format(hdr['dimensions']))

    rangex, rangey = hdr['scan_range']
    width = rangex[1] - rangex[0]
    height = rangey[1] - rangey[0]

    macros = eval(hdr['subscan_0']['macros'], dict(array=np.array))
    start_x, start_y = macros['scan_starts']
    dx = width / nx
    dy = height / ny
    grid_x = np.linspace(start_x, start_x + width + dx / 2, nx)
    grid_y = np.linspace(start_y, start_y + height + dy / 2, ny)

    if plot:
        mesh_x, mesh_y = np.meshgrid(grid_x, grid_y)
        plt.figure()
        if x_data is not None and y_data is not None:
            plt.scatter(x_data, y_data, c='blue', label='actual')
        plt.scatter(mesh_x, mesh_y, c='red', label='gridded',
                    alpha=0.5)
        plt.legend()
        plt.show()

    return grid_x, grid_y


def interp2d_scan(hdr, x_data, y_data, spectrum, *, kind='linear',
                  plot_points=False, **kwargs):
    '''Interpolate a 2D flyscan over a grid'''
    new_x, new_y = fly2d_grid(hdr, x_data, y_data, plot=plot_points)

    f = interp2d(x_data, y_data, spectrum, kind=kind, **kwargs)
    return f(new_x, new_y)


def interp1d_scan(hdr, x_data, y_data, spectrum, kind='linear',
                  plot_points=False, **kwargs):
    '''Interpolate a 2D flyscan only over the fast-scanning direction'''
    grid_x, grid_y = fly2d_grid(hdr, x_data, y_data, plot=plot_points)
    x_data = fly2d_reshape(hdr, x_data, verbose=False)

    spectrum2 = np.zeros_like(spectrum)
    for row in range(len(grid_y)):
        spectrum2[row, :] = interp1d(x_data[row, :], spectrum[row, :],
                                     kind=kind, bounds_error=False,
                                     **kwargs)(grid_x)

    return spectrum2


def fly2d_reshape(hdr, spectrum, verbose=True, copy=False):
    '''Reshape a 1D array to match the shape of a 2D flyscan'''
    info = ScanInfo(hdr)
    start_doc = hdr['start']

    try:
        nx, ny = info.dimensions
    except Exception:
        raise ValueError('Not a 2D flyscan (dimensions={})'
                         ''.format(info.dimensions))

    num = nx * ny
    spectrum = np.asarray(spectrum).flatten()

    if len(spectrum) < num:
        spectrum_ = np.ones(num) * np.min(spectrum)
        spectrum_[:len(spectrum)] = spectrum.flatten()
        spectrum = spectrum_
    elif copy:
        spectrum = spectrum.copy()

    try:
        spectrum = spectrum.reshape((ny, nx))
    except Exception as ex:
        if verbose:
            print('\tUnable to reshape data to (%d, %d) (%s: %s)'
                  '' % (nx, ny, ex.__class__.__name__, ex))
    else:
        fly_type = start_doc.get('fly_type', None)
        if fly_type in ('pyramid', ):
            # Pyramid scans' odd rows are flipped:
            subscan_dims = start_doc.get('subscan_dims', None)
            if subscan_dims is None:
                spectrum[1::2, :] = spectrum[1::2, ::-1]
            else:
                i = 0
                for nx, ny in subscan_dims:
                    start = i + 1
                    end = i + ny
                    spectrum[start:end:2, :] = spectrum[start:end:2, ::-1]
                    i += ny

        return spectrum
