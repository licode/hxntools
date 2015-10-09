import logging

from ophyd.controls import EpicsSignal
from ophyd.utils import DisconnectedError

logger = logging.getLogger(__name__)


class HxnUidBroadcast:
    '''Broadcast uid via PV

    Processed on every start/end document
    '''
    def __init__(self, uid_pv):
        self._uid = None
        self.uid_signal = EpicsSignal(uid_pv)

    @property
    def uid(self):
        '''The uid of the last scan run'''
        return self._uid

    @uid.setter
    def uid(self, uid):
        self._uid = uid

        if uid is None:
            uid = ''

        try:
            self.uid_signal.put(uid)
        except DisconnectedError:
            logger.error('UID PV disconnected. Is the hxntools IOC running?')

    def clear(self):
        '''Clear the scan uid'''
        self.uid = None

    def update(self):
        '''Set the uid from the last start document'''
        if self._last_start is None:
            return

        self.uid = self._last_start['uid']

    def __call__(self, name, doc):
        '''Bluesky callback with document info'''
        if name == 'start':
            self._last_start = doc
        if self._last_start and name in ('start', 'stop'):
            self.update()
