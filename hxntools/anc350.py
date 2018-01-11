import time
from ophyd import (Device, Component as Cpt)
from ophyd import (EpicsMotor, EpicsSignal)

import bluesky.plan_stubs as bps

anc350_dc_controllers = [2, 3, 4, 7]
# add 6 to this list if controller's moved back to the microscope rack
anc350_axis_counts = {1: 6,
                      2: 6,
                      3: 4,
                      4: 6,
                      5: 6,
                      6: 6,
                      7: 3,
                      # 8: 4,
                      }


class Anc350Axis(Device):
    motor = Cpt(EpicsMotor, 'Mtr')
    desc = Cpt(EpicsSignal, 'Mtr.DESC')
    frequency = Cpt(EpicsSignal, 'Freq-I', write_pv='Freq-SP')

    amplitude = Cpt(EpicsSignal, 'Ampl-I', write_pv='Ampl-SP')

    def __init__(self, prefix, *, axis_num=None, **kwargs):
        self.axis_num = int(axis_num)
        super(Anc350Axis, self).__init__(prefix, **kwargs)


class Anc350Controller(Device):
    dc_period = Cpt(EpicsSignal, 'DCPer-I', write_pv='DCPer-SP')
    dc_off_time = Cpt(EpicsSignal, 'DCOff-I', write_pv='DCOff-SP')
    dc_enable = Cpt(EpicsSignal, 'DC-I', write_pv='DC-Cmd')

    def __init__(self, prefix, **kwargs):
        super(Anc350Controller, self).__init__(prefix, **kwargs)

    def setup_dc(self, enable, period, off_time, verify=True):
        enable = 1 if enable else 0
        period = int(period)
        off_time = int(off_time)
        wait_group = 'anc_set_dc'

        yield from bps.abs_set(self.dc_period, period,
                               group=wait_group)
        yield from bps.abs_set(self.dc_off_time, off_time,
                               group=wait_group)
        yield from bps.abs_set(self.dc_enable, enable,
                               group=wait_group)
        if verify:
            yield from bps.wait(group=wait_group)


class HxnAnc350Axis(Anc350Axis):
    def __init__(self, controller, axis_num, **kwargs):
        prefix = 'XF:03IDC-ES{{ANC350:{}-Ax:{}}}'.format(controller, axis_num)
        name = f'anc_axis_{controller}'
        super().__init__(prefix, axis_num=axis_num, name=name, **kwargs)


class HxnAnc350Controller(Anc350Controller):
    def __init__(self, controller, **kwargs):
        prefix = 'XF:03IDC-ES{{ANC350:{}}}'.format(controller)
        name = f'anc_controller_{controller}'
        super().__init__(prefix, name=name, **kwargs)

        self.axes = {axis: HxnAnc350Axis(controller, axis)
                     for axis in range(anc350_axis_counts[controller])}


anc350_controllers = {controller: HxnAnc350Controller(controller)
                      for controller in anc350_axis_counts}


def _dc_status(controller, axis):
    pass


def _wait_tries(signal, value, tries=20, period=0.1):
    '''Wait up to `tries * period` for signal.get() to equal value'''

    # TODO set_and_wait?
    while tries > 0:
        tries -= 1
        if signal.get() == value:
            break

        time.sleep(period)


def _dc_toggle(axis, enable, freq, dc_period, off_time):
    print('Axis {} {}: '.format(axis.axis_num, axis.desc.value), end='')
    yield from bps.mov(axis.frequency, freq)
    print('frequency={}'.format(axis.frequency.get()))


def dc_toggle(enable, controllers=None, freq=100, dc_period=20, off_time=10):
    if controllers is None:
        controllers = anc350_dc_controllers

    for controller in controllers:
        print('Controller {}: '.format(controller), end='')
        controller = anc350_controllers[controller]

        try:
            yield from controller.setup_dc(enable, dc_period, off_time)
        except RuntimeError as ex:
            print('[Failed]', ex)
        except TimeoutError:
            print('Timed out - is the controller powered on?')
            continue
        else:
            if enable:
                print('Enabled duty cycling ({} off/{} on)'.format(
                      controller.dc_off_time.get(),
                      controller.dc_period.get()))
            else:
                print('Disabled duty cycling')

        for axis_num, axis in sorted(controller.axes.items()):
            print('\t', end='')
            yield from _dc_toggle(axis, enable, freq,
                                  dc_period, off_time)


def dc_on(*, frequency=100):
    yield from dc_toggle(True, freq=frequency)


def dc_off(*, frequency=1000):
    yield from dc_toggle(False, freq=frequency)
