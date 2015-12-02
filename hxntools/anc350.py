import time
from ophyd.controls.areadetector.detectors import (ADBase, ADSignal)
from ophyd.utils import TimeoutError


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


class Anc350Axis(ADBase):
    motor = ADSignal('Mtr', rw=True)
    desc = ADSignal('Mtr.DESC', rw=True)
    frequency = ADSignal('Freq-SP', rw=True)
    frequency_rbv = ADSignal('Freq-I')

    amplitude = ADSignal('Ampl-SP', rw=True)
    amplitude_rbv = ADSignal('Ampl-I')

    def __init__(self, prefix, axis_no, **kwargs):
        super(Anc350Axis, self).__init__(prefix, **kwargs)

        self.axis_no = axis_no


class Anc350Controller(ADBase):
    dc_period = ADSignal('DCPer-SP', rw=True)
    dc_off_time = ADSignal('DCOff-SP', rw=True)
    dc_enable = ADSignal('DC-Cmd', rw=True)

    dc_period_rbv = ADSignal('DCPer-I')
    dc_off_time_rbv = ADSignal('DCOff-I')
    dc_enable_rbv = ADSignal('DC-I')

    def __init__(self, prefix, **kwargs):
        super(Anc350Controller, self).__init__(prefix, **kwargs)

    def setup_dc(self, enable, period, off_time, verify=True):
        enable = 1 if enable else 0
        period = int(period)
        off_time = int(off_time)

        self.dc_period.put(period)
        self.dc_off_time.put(off_time)

        if verify:
            _wait_tries(self.dc_period_rbv, period)
            if period != self.dc_period_rbv.get():
                msg = ('Period not set correctly ({} != {})'
                       ''.format(period, self.dc_period_rbv.get()))
                raise RuntimeError('Period not set correctly')

            _wait_tries(self.dc_off_time_rbv, off_time)
            if off_time != self.dc_off_time_rbv.get():
                msg = ('Off time not set correctly ({} != {})'
                       ''.format(off_time, self.dc_off_time_rbv.get()))

                raise RuntimeError(msg)

        self.dc_enable.put(enable)

        if verify:
            _wait_tries(self.dc_enable, enable)
            if enable != self.dc_enable.get():
                msg = ('DC not enabled correctly ({} != {})'
                       ''.format(enable, self.dc_enable_rbv.get()))
                raise RuntimeError(msg)


class HxnAnc350Axis(Anc350Axis):
    def __init__(self, controller, axis_no, **kwargs):
        prefix = 'XF:03IDC-ES{{ANC350:{}-Ax:{}}}'.format(controller, axis_no)
        super(HxnAnc350Axis, self).__init__(prefix, axis_no, **kwargs)


class HxnAnc350Controller(Anc350Controller):
    def __init__(self, controller, **kwargs):
        prefix = 'XF:03IDC-ES{{ANC350:{}}}'.format(controller)
        super(HxnAnc350Controller, self).__init__(prefix, **kwargs)

        self.axes = {axis: HxnAnc350Axis(controller, axis)
                     for axis in range(anc350_axis_counts[controller])}


anc350_controllers = {controller: HxnAnc350Controller(controller)
                      for controller in anc350_axis_counts}


def _dc_status(controller, axis):
    pass


def _wait_tries(signal, value, tries=20, period=0.1):
    '''Wait up to `tries * period` for signal.get() to equal value'''

    while tries > 0:
        tries -= 1
        if signal.get() == value:
            break

        time.sleep(period)


def _dc_toggle(axis, enable, freq, dc_period, off_time):
    print('Axis {} {}: '.format(axis.axis_no, axis.desc.value), end='')
    axis.frequency.put(freq)
    _wait_tries(axis.frequency_rbv, freq)
    print('frequency={}'.format(axis.frequency_rbv.value))


def dc_toggle(enable, controllers=None, freq=100, dc_period=20, off_time=10):
    if controllers is None:
        controllers = anc350_dc_controllers

    for controller in controllers:
        print('Controller {}: '.format(controller), end='')
        controller = anc350_controllers[controller]

        try:
            controller.setup_dc(enable, dc_period, off_time)
        except RuntimeError as ex:
            print('[Failed]', ex)
        except TimeoutError:
            print('Timed out - is the controller powered on?')
            continue
        else:
            if enable:
                print('Enabled duty cycling ({} off/{} on)'.format(
                      controller.dc_off_time_rbv.value,
                      controller.dc_period.value))
            else:
                print('Disabled duty cycling')

        for axis_no, axis in sorted(controller.axes.items()):
            print('\t', end='')
            _dc_toggle(axis, enable, freq, dc_period, off_time)


def dc_on(*, frequency=100):
    dc_toggle(True, freq=frequency)


def dc_off(*, frequency=1000):
    dc_toggle(False, freq=frequency)
