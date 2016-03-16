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


# DerivedSignal: this may make it into ophyd at some point


class DerivedSignal(Signal):
    def __init__(self, derived_from, *, name=None, parent=None, **kwargs):
        '''A signal which is derived from another one
        Parameters
        ----------
        derived_from : Signal
            The signal from which this one is derived
        name : str, optional
            The signal name
        parent : Device, optional
            The parent device
        '''
        super().__init__(name=name, parent=parent, **kwargs)

        self._derived_from = derived_from
        if self._derived_from.connected:
            # set up the initial timestamp reporting, if connected
            self._timestamp = self._derived_from.timestamp

    @property
    def derived_from(self):
        '''Signal that this one is derived from'''
        return self._derived_from

    def describe(self):
        '''Description based on the original signal description'''
        desc = self._derived_from.describe()[self._derived_from.name]
        desc['derived_from'] = self._derived_from.name
        return {self.name: desc}

    def get(self, **kwargs):
        '''Get the value from the original signal'''
        value = self._derived_from.get(**kwargs)
        self._timestamp = self._derived_from.timestamp
        return value

    def put(self, value, **kwargs):
        '''Put the value to the original signal'''
        res = self._derived_from.put(value, **kwargs)
        self._timestamp = self._derived_from.timestamp
        return res

    def wait_for_connection(self, timeout=0.0):
        '''Wait for the original signal to connect'''
        return self._derived_from.wait_for_connection(timeout=timeout)

    @property
    def connected(self):
        '''Mirrors the connection state of the original signal'''
        return self._derived_from.connected

    @property
    def limits(self):
        '''Limits from the original signal'''
        return self._derived_from.limits

    def _repr_info(self):
        yield from super()._repr_info()
        yield ('derived_from', self._derived_from)


def ordered_dict_move_to_beginning(od, key):
    if key not in od:
        return

    value = od[key]
    items = list((k, v) for k, v in od.items()
                 if k != key)
    od.clear()
    od[key] = value
    od.update(items)
