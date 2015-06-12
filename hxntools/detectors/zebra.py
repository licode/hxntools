from __future__ import print_function
import logging
import threading
import time

from ophyd.controls.areadetector.detectors import (ADBase, ADSignal)
from ophyd.controls import EpicsSignal
from ophyd.controls.detector import (SignalDetector, DetectorStatus)

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

    addresses = {0: 'DISCONNECT',
                 1: 'IN1_TTL',
                 2: 'IN1_NIM',
                 3: 'IN1_LVDS',
                 4: 'IN2_TTL',
                 5: 'IN2_NIM',
                 6: 'IN2_LVDS',
                 7: 'IN3_TTL',
                 8: 'IN3_OC',
                 9: 'IN3_LVDS',
                 10: 'IN4_TTL',
                 11: 'IN4_CMP',
                 12: 'IN4_PECL',
                 13: 'IN5_ENCA',
                 14: 'IN5_ENCB',
                 15: 'IN5_ENCZ',
                 16: 'IN5_CONN',
                 17: 'IN6_ENCA',
                 18: 'IN6_ENCB',
                 19: 'IN6_ENCZ',
                 20: 'IN6_CONN',
                 21: 'IN7_ENCA',
                 22: 'IN7_ENCB',
                 23: 'IN7_ENCZ',
                 24: 'IN7_CONN',
                 25: 'IN8_ENCA',
                 26: 'IN8_ENCB',
                 27: 'IN8_ENCZ',
                 28: 'IN8_CONN',
                 29: 'PC_ARM',
                 30: 'PC_GATE',
                 31: 'PC_PULSE',
                 32: 'AND1',
                 33: 'AND2',
                 34: 'AND3',
                 35: 'AND4',
                 36: 'OR1',
                 37: 'OR2',
                 38: 'OR3',
                 39: 'OR4',
                 40: 'GATE1',
                 41: 'GATE2',
                 42: 'GATE3',
                 43: 'GATE4',
                 44: 'DIV1_OUTD',
                 45: 'DIV2_OUTD',
                 46: 'DIV3_OUTD',
                 47: 'DIV4_OUTD',
                 48: 'DIV1_OUTN',
                 49: 'DIV2_OUTN',
                 50: 'DIV3_OUTN',
                 51: 'DIV4_OUTN',
                 52: 'PULSE1',
                 53: 'PULSE2',
                 54: 'PULSE3',
                 55: 'PULSE4',
                 56: 'QUAD_OUTA',
                 57: 'QUAD_OUTB',
                 58: 'CLOCK_1KHZ',
                 59: 'CLOCK_1MHZ',
                 60: 'SOFT_IN1',
                 61: 'SOFT_IN2',
                 62: 'SOFT_IN3',
                 63: 'SOFT_IN4',
                 }

    soft_input1 = ADSignal('SOFT_IN:B0')
    soft_input2 = ADSignal('SOFT_IN:B1')
    soft_input3 = ADSignal('SOFT_IN:B2')
    soft_input4 = ADSignal('SOFT_IN:B3')

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

        for addr, addr_name in self.addresses.items():
            setattr(self, addr_name, addr)

    def step_scan(self, scan):
        pass

    def fly_scan(self, scan):
        pass


class ZebraPulseDetector(SignalDetector):
    def __init__(self, zebra, trigger=None, pulse=1,
                 trigger_value=None, **kwargs):
        if trigger is None:
            trigger = zebra.soft_input1
        if trigger_value is None:
            trigger_value = (1, 0)

        self._pulse_idx = pulse
        self._pulse = zebra.pulse[pulse].output
        self._pulse._name = '{}_pulse{}'.format(zebra.name, pulse)
        self._trigger = trigger
        self._trigger_value = trigger_value
        self._zebra = zebra

        super(ZebraPulseDetector, self).__init__(signal=self._pulse, **kwargs)

    def _run(self, status):
        time.sleep(self.wait_time + 0.01)
        status._finished()
        self._done_acquiring()

    @property
    def wait_time(self):
        pulse = self._zebra.pulse[self._pulse_idx]
        return pulse.width.value + pulse.delay.value

    def acquire(self, **kwargs):
        """Start acquisition"""
        for value in self._trigger_value:
            self._trigger.put(value)
            time.sleep(0.05)

        status = DetectorStatus(self)
        self._acq_thread = threading.Thread(target=self._run, args=(status, ))
        self._acq_thread.daemon = True
        self._acq_thread.start()
        return status


class HXNZebra(Zebra):
    def __init__(self, *args, **kwargs):
        super(HXNZebra, self).__init__(*args, **kwargs)

        # NOTE: preset_time comes from sync_dscan
        self.preset_time = None

    def _set_input_edges(self, gate, edge1, edge2):
        edge1, edge2 = int(edge1), int(edge2)
        while gate.input1_edge.value != edge1:
            gate.input1_edge.put(edge1)
            time.sleep(0.1)

        while gate.input2_edge.value != edge2:
            gate.input2_edge.put(edge2)
            time.sleep(0.1)

    def step_scan(self, scan):
        self.pulse[1].input1 = self.SOFT_IN1

        if self.preset_time is not None:
            self.pulse[1].width = self.preset_time
            self.pulse[1].delay = 0.0

        self.output[1].ttl = self.PULSE1
        self.output[2].ttl = self.PULSE1

        self.gate[2].input1 = self.PULSE1
        self.gate[2].input2 = self.PULSE1
        self._set_input_edges(self.gate[2], 1, 0)

        self.output[3].ttl = self.GATE2
        self.output[4].ttl = self.GATE2

    def fly_scan(self, scan):
        self.gate[1].input1 = self.IN3_OC
        self.gate[1].input2 = self.IN3_OC
        self._set_input_edges(self.gate[1], 1, 0)

        self.output[1].ttl = self.GATE1
        self.output[2].ttl = self.GATE1

        self.gate[2].input1 = self.IN3_OC
        self.gate[2].input2 = self.IN3_OC
        self._set_input_edges(self.gate[2], 0, 1)

        self.output[3].ttl = self.GATE2
        self.output[4].ttl = self.GATE2
