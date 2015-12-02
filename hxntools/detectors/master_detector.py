from __future__ import print_function
import logging


logger = logging.getLogger(__name__)


class MasterDetector(object):
    '''Hardware-trigger master detector
    '''

    def __init__(self, master, slaves=None, read_master=True):
        if slaves is None:
            slaves = []

        self._master = master
        self._slaves = list(slaves)
        self._read_master = bool(read_master)

    @property
    def count_time(self):
        return self._master.count_time

    @count_time.setter
    def count_time(self, count_time):
        self._master.count_time = count_time

    def trigger(self, *args, **kwargs):
        return self._master.trigger(*args, **kwargs)

    def configure(self, state=None):
        # TODO not sure how state should work here
        self._master.configure(state=state)
        for slave in self._slaves:
            slave.configure(state={})

    def deconfigure(self):
        self._master.deconfigure()
        for slave in self._slaves:
            slave.deconfigure()

    @property
    def master(self):
        return self._master

    @property
    def all_detectors(self):
        '''All detectors: master + slaves'''
        yield self._master
        yield from self._slaves

    @property
    def readable_detectors(self):
        '''Readable detectors: slaves and optionally the master'''
        if self._read_master:
            yield self._master

        yield from self._slaves

    __iter__ = readable_detectors

    def describe(self):
        '''Describe all readable detectors'''
        desc = {}
        for det in self.readable_detectors:
            desc.update(det.describe())
        return desc

    def read(self):
        '''Read from all readable detectors'''
        read = {}
        for det in self.readable_detectors:
            read.update(det.read())
        return read

    @property
    def slaves(self):
        '''All slave detectors'''
        return list(self._slaves)

    def add_slave(self, slave):
        '''Add a slave detector instance'''
        self._slaves.append(slave)

    def __iadd__(self, slave):
        self._slaves.append(slave)
        return self

    def remove_slave(self, slave):
        '''Remove a slave detector instance'''
        self._slaves.remove(slave)

    def __isub__(self, slave):
        self._slaves.remove(slave)
        return self

    def __delitem__(self, slave):
        self.remove_save(slave)

    def __contains__(self, slave):
        return slave in self._slaves

    def set(self, *args, **kwargs):
        '''Set detector parameters from bluesky'''
        for det in self.all_detectors:
            if hasattr(det, 'set'):
                det.set(*args, master=self, **kwargs)

    def __repr__(self):
        return ('{0.__class__.__name__}({0.master}, slaves={0.slaves}, '
                'read_master={0._read_master})'.format(self))

    def stop(self):
        # TODO bluesky implementation detail
        pass
