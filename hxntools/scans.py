import asyncio
import functools
import logging

from boltons.iterutils import chunked

from bluesky import (plans, spec_api, Msg)
from bluesky.global_state import get_gs
from bluesky import plan_patterns

from ophyd import (Device, Component as Cpt, EpicsSignal)
from .detectors.trigger_mixins import HxnModalBase

logger = logging.getLogger(__name__)


class ScanID(Device):
    next_scan_id_proc = Cpt(EpicsSignal, 'NextScanID-Cmd.PROC')
    scan_id = Cpt(EpicsSignal, 'ScanID-I')

    def get_next_scan_id(self):
        last_id = int(self.scan_id.get())
        self.next_scan_id_proc.put(1, wait=True)

        new_id = int(self.scan_id.get())
        if last_id == new_id:
            raise RuntimeError('Scan ID unchanged. Check hxnutil IOC.')
        return new_id


dev_scan_id = ScanID('XF:03IDC-ES{Status}', name='dev_scan_id')


def get_next_scan_id():
    dev_scan_id.wait_for_connection()
    return dev_scan_id.get_next_scan_id()


@asyncio.coroutine
def cmd_scan_setup(msg):
    detectors = msg.kwargs['detectors']
    total_points = msg.kwargs['total_points']
    count_time = msg.kwargs['count_time']

    modal_dets = [det for det in detectors
                  if isinstance(det, HxnModalBase)]

    mode = 'internal'
    for det in modal_dets:
        logger.debug('[internal trigger] Setting up detector %s', det.name)
        settings = det.mode_settings

        # Ensure count time is set prior to mode setup
        det.count_time.put(count_time)

        # start by using internal triggering
        settings.mode.put(mode)
        settings.scan_type.put('step')
        settings.total_points.put(total_points)
        det.mode_setup(mode)

    # the mode setup above should update to inform us which detectors
    # are externally triggered, in the form of the list in
    #   mode_settings.triggers
    # so update each of those to use external triggering
    triggered_dets = [det.mode_settings.triggers.get()
                      for det in modal_dets]
    triggered_dets = [triggers for triggers in triggered_dets
                      if triggers is not None]
    triggered_dets = set(sum(triggered_dets, []))

    logger.debug('These detectors will be externally triggered: %s',
                 ', '.join(det.name for det in triggered_dets))

    mode = 'external'
    for det in triggered_dets:
        logger.debug('[external trigger] Setting up detector %s', det)
        det.mode_settings.mode.put(mode)
        det.mode_setup(mode)


@asyncio.coroutine
def cmd_next_scan_id(msg):
    gs = get_gs()
    gs.RE.md['scan_id'] = get_next_scan_id() - 1


@asyncio.coroutine
def _debug_next_scan_id(cmd):
    print('debug_next_scan_id')
    gs = get_gs()
    gs.RE.md['scan_id'] = 0


def setup(*, debug_mode=False):
    gs = get_gs()
    gs.RE.register_command('hxn_scan_setup', cmd_scan_setup)

    if debug_mode:
        gs.RE.register_command('hxn_next_scan_id', _debug_next_scan_id)
    else:
        gs.RE.register_command('hxn_next_scan_id', cmd_next_scan_id)


def _pre_scan(total_points, count_time):
    gs = get_gs()
    yield Msg('hxn_next_scan_id')
    yield Msg('hxn_scan_setup', detectors=gs.DETS, total_points=total_points,
              count_time=count_time)


@functools.wraps(spec_api.ct)
def count(num=1, delay=None, time=None, *, md=None):
    yield from _pre_scan(total_points=num, count_time=time)
    yield from spec_api.ct(num=num, delay=delay, time=time, md=md)


@functools.wraps(spec_api.ascan)
def absolute_scan(motor, start, finish, intervals, time=None, *, md=None):
    yield from _pre_scan(total_points=intervals + 1, count_time=time)
    yield from spec_api.ascan(motor, start, finish, intervals, time, md=md)


@functools.wraps(spec_api.dscan)
def relative_scan(motor, start, finish, intervals, time=None, *, md=None):
    yield from _pre_scan(total_points=intervals + 1, count_time=time)
    yield from spec_api.dscan(motor, start, finish, intervals, time, md=md)


@functools.wraps(spec_api.afermat)
def absolute_fermat(x_motor, y_motor, x_start, y_start, x_range, y_range, dr,
                    factor, time=None, *, per_step=None, md=None, tilt=0.0):
    cyc = plan_patterns.spiral_fermat(x_motor, y_motor, x_motor.position,
                                      y_motor.position, x_range, y_range, dr,
                                      factor, tilt=tilt)
    total_points = len(cyc)

    yield from _pre_scan(total_points=total_points, count_time=time)
    yield from spec_api.afermat(x_motor, y_motor, x_start, y_start, x_range,
                                y_range, dr, factor, time=time,
                                per_step=per_step, md=md)


@functools.wraps(spec_api.fermat)
def relative_fermat(x_motor, y_motor, x_range, y_range, dr, factor, time=None,
                    *, per_step=None, md=None, tilt=0.0):
    cyc = plan_patterns.spiral_fermat(x_motor, y_motor, x_motor.position,
                                      y_motor.position, x_range, y_range, dr,
                                      factor, tilt=tilt)
    total_points = len(cyc)

    yield from _pre_scan(total_points=total_points, count_time=time)
    yield from spec_api.fermat(x_motor, y_motor, x_range, y_range, dr, factor,
                               time=time, per_step=per_step, md=md)


@functools.wraps(spec_api.aspiral)
def absolute_spiral(x_motor, y_motor, x_start, y_start, x_range, y_range, dr,
                    nth, time=None, *, per_step=None, md=None, tilt=0.0):
    cyc = plan_patterns.spiral_simple(x_motor, y_motor, x_motor.position,
                                      y_motor.position, x_range, y_range, dr,
                                      nth, tilt=tilt)
    total_points = len(cyc)

    yield from _pre_scan(total_points=total_points, count_time=time)
    yield from spec_api.aspiral(x_motor, y_motor, x_start, y_start, x_range,
                                y_range, dr, nth, time=time,
                                per_step=per_step, md=md)


@functools.wraps(spec_api.spiral)
def relative_spiral(x_motor, y_motor, x_range, y_range, dr, nth, time=None,
                    *, per_step=None, md=None, tilt=0.0):
    cyc = plan_patterns.spiral_simple(x_motor, y_motor, x_motor.position,
                                      y_motor.position, x_range, y_range, dr,
                                      nth, tilt=tilt)
    total_points = len(cyc)

    yield from _pre_scan(total_points=total_points, count_time=time)
    yield from spec_api.spiral(x_motor, y_motor, x_range, y_range, dr, nth,
                               time=time, per_step=per_step, md=md)


@functools.wraps(spec_api.mesh)
def absolute_mesh(*args, time=None, md=None):
    if (len(args) % 4) == 1:
        if time is not None:
            raise ValueError('wrong number of positional arguments')
        args, time = args[:-1], args[-1]

    total_points = 1
    for motor, start, stop, num in chunked(args, 4):
        total_points *= num

    yield from _pre_scan(total_points=total_points, count_time=time)
    yield from spec_api.mesh(*args, time=time, md=md)


@functools.wraps(absolute_mesh)
def relative_mesh(*args, time=None, md=None):
    plan = absolute_mesh(*args, time=time, md=md)
    plan = plans.relative_set(plan)  # re-write trajectory as relative
    yield from plans.reset_positions(plan)
