from enum import IntEnum
import logging
import time

from ophyd import (Device, Component as Cpt,
                   FormattedComponent as FC)
from ophyd import (EpicsSignal, EpicsSignalRO, DeviceStatus)
from ophyd.utils import set_and_wait

logger = logging.getLogger(__name__)


class ZebraAddresses(IntEnum):
    DISCONNECT = 0
    IN1_TTL = 1
    IN1_NIM = 2
    IN1_LVDS = 3
    IN2_TTL = 4
    IN2_NIM = 5
    IN2_LVDS = 6
    IN3_TTL = 7
    IN3_OC = 8
    IN3_LVDS = 9
    IN4_TTL = 10
    IN4_CMP = 11
    IN4_PECL = 12
    IN5_ENCA = 13
    IN5_ENCB = 14
    IN5_ENCZ = 15
    IN5_CONN = 16
    IN6_ENCA = 17
    IN6_ENCB = 18
    IN6_ENCZ = 19
    IN6_CONN = 20
    IN7_ENCA = 21
    IN7_ENCB = 22
    IN7_ENCZ = 23
    IN7_CONN = 24
    IN8_ENCA = 25
    IN8_ENCB = 26
    IN8_ENCZ = 27
    IN8_CONN = 28
    PC_ARM = 29
    PC_GATE = 30
    PC_PULSE = 31
    AND1 = 32
    AND2 = 33
    AND3 = 34
    AND4 = 35
    OR1 = 36
    OR2 = 37
    OR3 = 38
    OR4 = 39
    GATE1 = 40
    GATE2 = 41
    GATE3 = 42
    GATE4 = 43
    DIV1_OUTD = 44
    DIV2_OUTD = 45
    DIV3_OUTD = 46
    DIV4_OUTD = 47
    DIV1_OUTN = 48
    DIV2_OUTN = 49
    DIV3_OUTN = 50
    DIV4_OUTN = 51
    PULSE1 = 52
    PULSE2 = 53
    PULSE3 = 54
    PULSE4 = 55
    QUAD_OUTA = 56
    QUAD_OUTB = 57
    CLOCK_1KHZ = 58
    CLOCK_1MHZ = 59
    SOFT_IN1 = 60
    SOFT_IN2 = 61
    SOFT_IN3 = 62
    SOFT_IN4 = 63


class EpicsSignalWithRBV(EpicsSignal):
    # An EPICS signal that uses the Zebra convention of 'pvname' being the
    # setpoint and 'pvname:RBV' being the read-back

    def __init__(self, prefix, **kwargs):
        super().__init__(prefix + ':RBV', write_pv=prefix, **kwargs)


class ZebraPulse(Device):
    width = Cpt(EpicsSignalWithRBV, 'WID')
    input_addr = Cpt(EpicsSignalWithRBV, 'INP')
    input_str = Cpt(EpicsSignalRO, 'INP:STR', string=True)
    input_status = Cpt(EpicsSignalRO, 'INP:STA')
    delay = Cpt(EpicsSignalWithRBV, 'DLY')
    time_units = Cpt(EpicsSignalWithRBV, 'PRE', string=True)
    output = Cpt(EpicsSignal, 'OUT')

    input_edge_1 = FC(EpicsSignal, '{self.parent.prefix}POLARITY:BC')
    input_edge_2 = FC(EpicsSignal, '{self.parent.prefix}POLARITY:BD')
    input_edge_3 = FC(EpicsSignal, '{self.parent.prefix}POLARITY:BE')
    input_edge_4 = FC(EpicsSignal, '{self.parent.prefix}POLARITY:BF')

    def __init__(self, prefix, *, index=None, **kwargs):
        self.index = index
        super().__init__(prefix, **kwargs)


class ZebraOutput(Device):
    def __init__(self, prefix, *, index=None, **kwargs):
        self.index = index
        super().__init__(prefix, **kwargs)

# Front outputs
# # TTL  LVDS  NIM  PECL  OC
# 1  o    o     o
# 2  o    o     o
# 3  o    o               o
# 4  o          o    o

class ZebraFrontOutput12(ZebraOutput):
    ttl = Cpt(EpicsSignalWithRBV, 'TTL')
    lvds = Cpt(EpicsSignalWithRBV, 'LVDS')
    nim = Cpt(EpicsSignalWithRBV, 'NIM')


class ZebraFrontOutput3(ZebraOutput):
    ttl = Cpt(EpicsSignalWithRBV, 'TTL')
    lvds = Cpt(EpicsSignalWithRBV, 'LVDS')
    open_collector = Cpt(EpicsSignalWithRBV, 'OC')


class ZebraFrontOutput4(ZebraOutput):
    ttl = Cpt(EpicsSignalWithRBV, 'TTL')
    nim = Cpt(EpicsSignalWithRBV, 'NIM')
    pecl = Cpt(EpicsSignalWithRBV, 'PECL')


class ZebraRearOutput(ZebraOutput):
    enca = Cpt(EpicsSignalWithRBV, 'ENCA')
    encb = Cpt(EpicsSignalWithRBV, 'ENCB')
    encz = Cpt(EpicsSignalWithRBV, 'ENCZ')
    conn = Cpt(EpicsSignalWithRBV, 'CONN')


class ZebraGate(Device):
    input1 = Cpt(EpicsSignalWithRBV, 'INP1')
    input1_string = Cpt(EpicsSignalRO, 'INP1:STR', string=True)
    input1_status = Cpt(EpicsSignalRO, 'INP1:STA', string=True)

    input2 = Cpt(EpicsSignalWithRBV, 'INP2')
    input2_string = Cpt(EpicsSignalRO, 'INP2:STR', string=True)
    input2_status = Cpt(EpicsSignalRO, 'INP2:STA', string=True)

    output = Cpt(EpicsSignal, 'OUT')

    # Input edge index depends on the gate number (these are set in __init__)
    input1_edge = FC(EpicsSignal,
                     '{self.parent.prefix}POLARITY:B{self._input1_edge_idx}')
    input2_edge = FC(EpicsSignal,
                     '{self.parent.prefix}POLARITY:B{self._input2_edge_idx}')

    def __init__(self, prefix, *, index, **kwargs):
        self.index = index
        self._input1_edge_idx = index - 1
        self._input2_edge_idx = 4 + index - 1

        super().__init__(prefix, **kwargs)

    def set_input_edges(self, edge1, edge2):
        set_and_wait(self.input1_edge, int(edge1))
        set_and_wait(self.input2_edge, int(edge2))


class Zebra(Device):
    soft_input1 = Cpt(EpicsSignal, 'SOFT_IN:B0')
    soft_input2 = Cpt(EpicsSignal, 'SOFT_IN:B1')
    soft_input3 = Cpt(EpicsSignal, 'SOFT_IN:B2')
    soft_input4 = Cpt(EpicsSignal, 'SOFT_IN:B3')

    pulse1 = Cpt(ZebraPulse, 'PULSE1_', index=1)
    pulse2 = Cpt(ZebraPulse, 'PULSE2_', index=2)
    pulse3 = Cpt(ZebraPulse, 'PULSE3_', index=3)
    pulse4 = Cpt(ZebraPulse, 'PULSE4_', index=4)

    output1 = Cpt(ZebraFrontOutput12, 'OUT1_', index=1)
    output2 = Cpt(ZebraFrontOutput12, 'OUT2_', index=2)
    output3 = Cpt(ZebraFrontOutput3, 'OUT3_', index=3)
    output4 = Cpt(ZebraFrontOutput4, 'OUT4_', index=4)

    output5 = Cpt(ZebraRearOutput, 'OUT5_', index=5)
    output6 = Cpt(ZebraRearOutput, 'OUT6_', index=6)
    output7 = Cpt(ZebraRearOutput, 'OUT7_', index=7)
    output8 = Cpt(ZebraRearOutput, 'OUT8_', index=8)

    gate1 = Cpt(ZebraGate, 'GATE1_', index=1)
    gate2 = Cpt(ZebraGate, 'GATE2_', index=2)
    gate3 = Cpt(ZebraGate, 'GATE3_', index=3)
    gate4 = Cpt(ZebraGate, 'GATE4_', index=4)

    addresses = ZebraAddresses

    def __init__(self, prefix, *, scan_modes=None, **kwargs):
        super().__init__(prefix, **kwargs)

        self.pulse = dict(self._get_indexed_devices(ZebraPulse))
        self.output = dict(self._get_indexed_devices(ZebraOutput))
        self.gate = dict(self._get_indexed_devices(ZebraGate))

        if scan_modes is None:
            scan_modes = {}

        self._scan_modes = scan_modes

    def _get_indexed_devices(self, cls):
        for attr in self._sub_devices:
            dev = getattr(self, attr)
            if isinstance(dev, cls):
                yield dev.index, dev

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

    def configure(self, state=None):
        pass

    def deconfigure(self):
        pass

    def trigger(self):
        # Re-implement this to trigger as desired in bluesky
        status = DeviceStatus(self)
        status._finished()
        return status

    def describe(self):
        return {}

    def read(self):
        return {}

    def stop(self):
        pass


class HXNZebra(Zebra):
    def __init__(self, prefix, **kwargs):
        scan_modes = dict(step_scan=self.step_scan,
                          fly_scan=self.fly_scan)
        super().__init__(prefix, scan_modes=scan_modes, **kwargs)

        # NOTE: count_time comes from bluesky
        self.count_time = None
        self._mode = None

    def step_scan(self):
        super().step_scan()

        # Scaler triggers all detectors
        # Scaler, output mode 1, LNE (output 5) connected to Zebra IN1_TTL
        # Pulse 1 has pulse width set to the count_time

        # OUT1_TTL Merlin
        # OUT2_TTL Scaler 1 inhibit
        #
        # OUT3_TTL Scaler 1 gate
        # OUT4_TTL Xspress3
        self.pulse[1].input_addr.put(ZebraAddresses.IN1_TTL)

        if self.count_time is not None:
            logger.debug('Step scan pulse-width is %s', self.count_time)
            self.pulse[1].width.put(ZebraAddresses.count_time)
            self.pulse[1].time_units.value = 's'

        self.pulse[1].delay.value = 0.0
        self.pulse[1].input_edge.value = 1

        # To be used in regular scaler mode, scaler 1 has to have
        # inhibit cleared and counting enabled:
        self.soft_input4.value = 1

        # Timepix
        # self.output[1].ttl = self.PULSE1
        # Merlin
        self.output[1].ttl.put(ZebraAddresses.PULSE1)
        self.output[2].ttl.put(ZebraAddresses.SOFT_IN4)

        self.gate[2].input1.put(ZebraAddresses.PULSE1)
        self.gate[2].input2.put(ZebraAddresses.PULSE1)
        self.gate[2].set_input_edges(0, 1)

        self.output[3].ttl.put(ZebraAddresses.SOFT_IN4)
        self.output[4].ttl.put(ZebraAddresses.GATE2)

        # Merlin LVDS
        self.output[1].lvds.put(ZebraAddresses.PULSE1)

    def fly_scan(self):
        super().fly_scan()

        self.gate[1].input1.put(ZebraAddresses.IN3_OC)
        self.gate[1].input2.put(ZebraAddresses.IN3_OC)
        self.gate[1].set_input_edges(1, 0)

        # timepix:
        # self.output[1].ttl = self.GATE1
        # merlin:
        # (Merlin is now on TTL 1 output, replacing timepix 1)
        self.output[1].ttl.put(ZebraAddresses.GATE2)
        self.output[2].ttl.put(ZebraAddresses.GATE1)

        self.gate[2].input1.put(ZebraAddresses.IN3_OC)
        self.gate[2].input2.put(ZebraAddresses.IN3_OC)
        self.gate[2].set_input_edges(0, 1)

        self.output[3].ttl.put(ZebraAddresses.GATE2)
        self.output[4].ttl.put(ZebraAddresses.GATE2)

        # Merlin LVDS
        # self.output[1].lvds.put(ZebraAddresses.GATE2)

    def set(self, total_points=None, scan_mode='step_scan', **kwargs):
        self.scan_mode = scan_mode
