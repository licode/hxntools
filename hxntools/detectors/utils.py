from __future__ import print_function
import os
from ophyd import Signal


def makedirs(path, mode=0o777):
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


def ordered_dict_move_to_beginning(od, key):
    if key not in od:
        return

    value = od[key]
    items = list((k, v) for k, v in od.items()
                 if k != key)
    od.clear()
    od[key] = value
    od.update(items)
