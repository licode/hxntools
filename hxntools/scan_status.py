import logging

from ophyd import EpicsSignal
from ophyd.utils import DisconnectedError

logger = logging.getLogger(__name__)


class HxnScanStatus:
    '''Broadcast if a scan is in progress via PV

    Processed on every start/end document
    '''
    def __init__(self, running_pv):
        self._last_start = None
        self.running_signal = EpicsSignal(running_pv)
        self._running = False

    @property
    def running(self):
        return self._running

    @running.setter
    def running(self, running):
        self._running = running

        if running is None:
            running = 0

        try:
            self.running_signal.put(running)
        except DisconnectedError:
            logger.error('ScanRunning PV disconnected. Is the hxntools IOC running?')

    def __call__(self, name, doc):
        '''Bluesky callback with document info'''
        if name == 'start':
            self._last_start = doc
        if self._last_start and name in ('start', 'stop'):
            self.running = (name == 'start')
