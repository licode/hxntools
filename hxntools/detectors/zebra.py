from __future__ import print_function
import logging
import time

from ophyd.controls.areadetector.detectors import (ADBase, ADSignal)
from ophyd.controls import EpicsSignal
from ophyd.controls.ophydobj import DetectorStatus

logger = logging.getLogger(__name__)


class ZebraPulse(ADBase):
    _html_docs = ['']

    width = ADSignal('WID')
    input_ = ADSignal('INP')
    input_str = ADSignal('INP:STR', rw=False, string=True)
    input_status = ADSignal('INP:STA', rw=False)
    delay = ADSignal('DLY')
    time_units = ADSignal('PRE', string=True)
    output = ADSignal('OUT')

    def __init__(self, prefix, zebra, index, **kwargs):
        super(ZebraPulse, self).__init__(prefix, **kwargs)

        self._zebra = zebra
        self._index = index

        input_edge = {1: '{}POLARITY:BC',
                      2: '{}POLARITY:BD',
                      3: '{}POLARITY:BE',
                      4: '{}POLARITY:BF',
                      }

        self.input_edge = EpicsSignal(input_edge[index].format(zebra._prefix),
                                      alias='input_edge')


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

        self.pulse = {i: ZebraPulse('{}PULSE{}_'.format(self._prefix, i),
                                    self, i)
                      for i in range(1, 5)}
        self.output = {i: ZebraFrontOutput('{}OUT{}_'.format(self._prefix, i))
                       for i in range(1, 5)}

        for i in range(5, 9):
            out_prefix = '{}OUT{}_'.format(self._prefix, i)
            self.output[i] = ZebraRearOutput(out_prefix)

        self.gate = {i: ZebraGate('{}GATE{}_'.format(self._prefix, i), self, i)
                     for i in range(1, 5)}

        for addr, addr_name in self.addresses.items():
            setattr(self, addr_name, addr)

        self._scan_modes = {'step_scan': self.step_scan,
                            'fly_scan': self.fly_scan
                            }

    def step_scan(self):
        logger.debug('Zebra %s: configuring step-scan mode', self)

    def fly_scan(self):
        logger.debug('Zebra %s: configuring fly-scan mode', self)

    @property
    def scan_mode(self):
        '''The scanning scan_mode'''
        return self._scan_mode

    @scan_mode.setter
    def scan_mode(self, scan_mode):
        try:
            mode_setup = self._scan_modes[scan_mode]
        except KeyError:
            raise ValueError('Unrecognized scan mode {!r}. Available: {}'
                             ''.format(scan_mode, self._scan_modes.keys()))

        mode_setup()
        self._scan_mode = scan_mode

    def configure(self):
        pass

    def deconfigure(self):
        pass

    def trigger(self):
        # Re-implement this to trigger as desired in bluesky
        status = DetectorStatus(self)
        status._finished()
        return status

    def describe(self):
        return {}

    def read(self):
        return {}

    def stop(self):
        # TODO bluesky implementation detail
        pass


class HXNZebra(Zebra):
    def __init__(self, *args, **kwargs):
        super(HXNZebra, self).__init__(*args, **kwargs)

        # NOTE: count_time comes from bluesky
        self.count_time = None
        self._mode = None

    def _set_input_edges(self, gate, edge1, edge2):
        edge1, edge2 = int(edge1), int(edge2)
        while gate.input1_edge.value != edge1:
            gate.input1_edge.put(edge1)
            time.sleep(0.1)

        while gate.input2_edge.value != edge2:
            gate.input2_edge.put(edge2)
            time.sleep(0.1)

    def step_scan(self):
        super(HXNZebra, self).step_scan()

        # Scaler triggers all detectors
        # Scaler, output mode 1, LNE (output 5) connected to Zebra IN1_TTL
        # Pulse 1 has pulse width set to the count_time

        # OUT1_TTL Merlin
        # OUT2_TTL Scaler 1 inhibit
        #
        # OUT3_TTL Scaler 1 gate
        # OUT4_TTL Xspress3
        self.pulse[1].input_.value = self.IN1_TTL

        if self.count_time is not None:
            logger.debug('Step scan pulse-width is %s', self.count_time)
            self.pulse[1].width.value = self.count_time
            self.pulse[1].time_units.value = 's'

        self.pulse[1].delay.value = 0.0
        self.pulse[1].input_edge.value = 1

        # To be used in regular scaler mode, scaler 1 has to have
        # inhibit cleared and counting enabled:
        self.soft_input4.value = 1

        # Timepix
        # self.output[1].ttl = self.PULSE1
        # Merlin
        self.output[1].ttl.value = self.PULSE1
        self.output[2].ttl.value = self.SOFT_IN4

        self.gate[2].input1.value = self.PULSE1
        self.gate[2].input2.value = self.PULSE1
        self._set_input_edges(self.gate[2], 0, 1)

        self.output[3].ttl.value = self.SOFT_IN4
        self.output[4].ttl.value = self.GATE2

        # Merlin LVDS
        self.output[1].lvds.value = self.PULSE1

    def fly_scan(self):
        super(HXNZebra, self).fly_scan()

        self.gate[1].input1.value = self.IN3_OC
        self.gate[1].input2.value = self.IN3_OC
        self._set_input_edges(self.gate[1], 1, 0)

        # timepix:
        # self.output[1].ttl = self.GATE1
        # merlin:
        # (Merlin is now on TTL 1 output, replacing timepix 1)
        self.output[1].ttl.value = self.GATE2
        self.output[2].ttl.value = self.GATE1

        self.gate[2].input1.value = self.IN3_OC
        self.gate[2].input2.value = self.IN3_OC
        self._set_input_edges(self.gate[2], 0, 1)

        self.output[3].ttl.value = self.GATE2
        self.output[4].ttl.value = self.GATE2

        # Merlin LVDS
        # self.output[1].lvds.value = self.GATE2

    def set(self, total_points=None, scan_mode='step_scan', **kwargs):
        self.scan_mode = scan_mode
