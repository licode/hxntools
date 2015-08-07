from __future__ import print_function
import logging

from ophyd.controls import EpicsSignal
from ophyd.controls.detector import (Detector, DetectorStatus)


logger = logging.getLogger(__name__)
sr_shutter_status = EpicsSignal('SR-EPS{PLC:1}Sts:MstrSh-Sts', rw=False,
                                name='sr_shutter_status')
sr_beam_current = EpicsSignal('SR:C03-BI{DCCT:1}I:Real-I', rw=False,
                              name='sr_beam_current')


class BeamStatusDetector(Detector):
    def __init__(self, *args, **kwargs):
        self._shutter_status = kwargs.pop('shutter_status', sr_shutter_status)
        self._beam_current = kwargs.pop('beam_current', sr_beam_current)
        self._min_current = kwargs.pop('min_current', 100.0)

        Detector.__init__(self, *args, **kwargs)

        self._shutter_ok = False
        self._current_ok = False
        self._last_status = None
        self._statuses = []

        self._shutter_status.subscribe(self._shutter_changed)
        self._beam_current.subscribe(self._current_changed)

    def acquire(self):
        status = DetectorStatus(self)

        if self.status:
            status.done = True
        else:
            self._statuses.append(status)

        return status

    def _shutter_changed(self, value=None, **kwargs):
        self._shutter_ok = (value == 1)
        self._check_status()

    def _current_changed(self, value=None, **kwargs):
        self._current_ok = (value > self._min_current)
        self._check_status()

    def _done(self):
        for status in self._statuses:
            status.done = True

    @property
    def status(self):
        return self._shutter_ok and self._current_ok

    def _check_status(self):
        status = self.status

        if status:
            self._done()

        if status != self._last_status:
            logger.warning('Beam status changed:')

            if self._shutter_ok:
                logger.warning('Shutters are open')
            else:
                logger.warning('Shutters are closed')

            if self._current_ok:
                logger.warning('Current meets threshold of %f' %
                               self._min_current)
            else:
                logger.warning('Current does not meet threshold of %f' %
                               self._min_current)

        self._last_status = status

    def read(self):
        del self._statuses[:]
        return [self._beam_current.read(), self._shutter_status.read()]

    def describe(self):
        return [self._beam_current.describe(), self._shutter_status.describe()]
