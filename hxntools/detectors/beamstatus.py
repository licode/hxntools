from __future__ import print_function
import logging

from ophyd import (EpicsSignalRO, DeviceStatus)
from ophyd import (Device, Component as Cpt)

logger = logging.getLogger(__name__)


class BeamStatusDetector(Device):
    shutter_status = Cpt(EpicsSignalRO, 'SR-EPS{PLC:1}Sts:MstrSh-Sts')
    beam_current = Cpt(EpicsSignalRO, 'SR:C03-BI{DCCT:1}I:Real-I')
    enabled = Cpt(EpicsSignalRO, 'SR:C03-EPS{PLC:1}Sts:ID_BE_Enbl-Sts')

    def __init__(self, prefix='', *, min_current=100.0, read_attrs=None,
                 configuration_attrs=None,
                 **kwargs):
        self._min_current = min_current

        if configuration_attrs is None:
            configuration_attrs = ['shutter_status', 'enabled', 'beam_current']
        if read_attrs is None:
            read_attrs = ['beam_current']

        super().__init__(prefix, configuration_attrs=configuration_attrs,
                         read_attrs=read_attrs, **kwargs)

        self._shutter_ok = None
        self._current_ok = None
        self._enabled_ok = None
        self._last_status = None
        self._statuses = []

        self.shutter_status.subscribe(self._shutter_changed)
        self.beam_current.subscribe(self._current_changed)
        self.enabled.subscribe(self._enabled_changed)

    @property
    def min_current(self):
        '''The minimum current required to be considered usable'''
        return self._min_current

    @min_current.setter
    def min_current(self, value):
        '''The minimum current required to be considered usable'''
        self._min_current = value
        self._current_changed(value=self.sr_beam_current.get())

    def _shutter_changed(self, value=None, **kwargs):
        self._shutter_ok = (value == 1)
        self._check_status()

    def _current_changed(self, value=None, **kwargs):
        self._current_ok = (value > self._min_current)
        self._check_status()

    def _enabled_changed(self, value=None, **kwargs):
        self._enabled_ok = (value == 1)
        self._check_status()

    @property
    def status(self):
        return self._shutter_ok and self._current_ok and self._enabled_ok

    def _check_status(self):
        if None in (self._shutter_ok, self._current_ok, self._enabled_ok):
            return

        status = self.status

        if status:
            self._done()

        if status != self._last_status:
            logger.warning('Beam status changed:')

            if self._enabled_ok:
                logger.warning('Beamline is enabled')
            else:
                logger.warning('Beamline is NOT enabled')

            if self._shutter_ok:
                logger.warning('Shutters are open')
            else:
                logger.warning('Shutters are closed')

            if self._current_ok:
                logger.warning('Current meets threshold of %f',
                               self.min_current)
            else:
                logger.warning('Current does not meet threshold of %f',
                               self.min_current)

        self._last_status = status

    def _done(self):
        for status in self._statuses:
            status._finished()

    def trigger(self):
        status = DeviceStatus(self)

        if self.status:
            status._finished()
        else:
            self._statuses.append(status)

        if not status.done:
            logger.warning('---')
            logger.warning('Waiting for beam status to change...')
            logger.warning('---')

        return status

    def read(self):
        del self._statuses[:]
        return super().read()
