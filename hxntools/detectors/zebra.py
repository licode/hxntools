from __future__ import print_function
import logging

from ophyd.controls.areadetector.detectors import (ADBase, ADSignal)
from ophyd.controls import EpicsSignal

logger = logging.getLogger(__name__)


class ZebraPulse(ADBase):
    _html_docs = ['']

    width = ADSignal('WID')
    input_ = ADSignal('INP')
    input_str = ADSignal('INP:STR', rw=False, string=True)
    input_status = ADSignal('INP:STA', rw=False)
    delay = ADSignal('DLY')
    time_units = ADSignal('PRE')
    output = ADSignal('OUT')


class ZebraFrontOutput(ADBase):
    _html_docs = ['']

    ttl = ADSignal('TTL')
    nim = ADSignal('NIM')
    lvds = ADSignal('LVDS')
    open_collector = ADSignal('OC')
    pecl = ADSignal('PECL')


class ZebraRearOutput(ADBase):
    _html_docs = ['']

    enca = ADSignal('ENCA')
    encb = ADSignal('ENCB')
    encz = ADSignal('ENCZ')
    conn = ADSignal('CONN')


class ZebraGate(ADBase):
    _html_docs = ['']

    input1 = ADSignal('INP1')
    input1_string = ADSignal('INP1:STR', string=True, rw=False)
    input1_status = ADSignal('INP1:STA', string=True, rw=False)

    input2 = ADSignal('INP2')
    input2_string = ADSignal('INP2:STR', string=True, rw=False)
    input2_status = ADSignal('INP2:STA', string=True, rw=False)

    output = ADSignal('OUT')

    def __init__(self, prefix, zebra, index, **kwargs):
        super(ZebraGate, self).__init__(prefix, **kwargs)

        # TODO not adsignals, so can't use setter
        # NOTE prefix is using zebra's prefix not gate's
        inp1_b = '{}POLARITY:B{}'.format(zebra._prefix, index - 1)
        self.input1_edge = EpicsSignal(inp1_b, alias='input1_edge')

        inp2_b = '{}POLARITY:B{}'.format(zebra._prefix, 4 + index - 1)
        self.input2_edge = EpicsSignal(inp2_b, alias='input2_edge')


class Zebra(ADBase):
    _html_docs = ['']

    def __init__(self, *args, **kwargs):
        super(Zebra, self).__init__(*args, **kwargs)

        self.pulse = {i: ZebraPulse('{}PULSE{}_'.format(self._prefix, i))
                      for i in range(1, 5)}
        self.output = {i: ZebraFrontOutput('{}OUT{}_'.format(self._prefix, i))
                       for i in range(1, 5)}

        for i in range(5, 9):
            self.output[i] = ZebraRearOutput('{}OUT{}_'.format(self._prefix, i))

        self.gate = {i: ZebraGate('{}GATE{}_'.format(self._prefix, i), self, i)
                     for i in range(1, 5)}
