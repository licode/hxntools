from __future__ import print_function
import os
import numpy as np


def makedirs(path, mode=0777):
    '''Recursively make directories and set permissions'''
    # Permissions not working with os.makedirs -
    # See: http://stackoverflow.com/questions/5231901
    if not path or os.path.exists(path):
        return []

    head, tail = os.path.split(path)
    ret = makedirs(head, mode)
    try:
        os.mkdir(path)
    except OSError as ex:
        if 'File exists' not in str(ex):
            raise

    os.chmod(path, mode)
    ret.append(path)
    return ret


def get_total_scan_points(points):
    '''
    points : ndarray, list, or integer

    returns: product of all points
    '''
    points = np.asarray(points)
    return np.prod(points)
