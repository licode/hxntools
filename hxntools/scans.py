import asyncio
import functools
import ophyd
import logging
from collections import deque

from boltons.iterutils import chunked
from cycler import cycler

from bluesky import (plans, spec_api, Msg)
from bluesky.global_state import get_gs
from bluesky.callbacks import LiveTable, LivePlot, LiveRaster

from ophyd import (Device, Component as Cpt, EpicsSignal)
from .detectors.trigger_mixins import HxnModalBase
from . import scan_patterns

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

    modal_dets = [det for det in detectors
                  if isinstance(det, HxnModalBase)]

    mode = 'internal'
    for det in detectors:
        logger.debug('[internal trigger] Setting up detector %s', det.name)
        settings = det.mode_settings

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


def setup():
    gs = get_gs()
    gs.RE.register_command('hxn_scan_setup', cmd_scan_setup)

    # TODO debugging
    # gs.RE.register_command('hxn_next_scan_id', cmd_next_scan_id)
    gs.RE.register_command('hxn_next_scan_id', _debug_next_scan_id)


def _pre_scan(total_points):
    gs = get_gs()
    yield Msg('hxn_next_scan_id')
    yield Msg('hxn_scan_setup', detectors=gs.DETS, total_points=total_points)


@functools.wraps(spec_api.ascan)
def absolute_scan(motor, start, finish, intervals, time=None, **kwargs):
    yield from _pre_scan(total_points=intervals + 1)
    yield from spec_api.ascan(motor, start, finish, intervals, time, **kwargs)


@functools.wraps(spec_api.dscan)
def relative_scan(motor, start, finish, intervals, time=None, **kwargs):
    yield from _pre_scan(total_points=intervals + 1)
    yield from spec_api.dscan(motor, start, finish, intervals, time, **kwargs)


@plans.planify
def absolute_fermat(x_motor, y_motor, x_range, y_range, dr, factor, time=None,
                    *, per_step=None, md=None):
    '''Absolute fermat spiral scan, centered around (0, 0)

    Parameters
    ----------
    x_motor : object
        any 'setable' object (motor, temp controller, etc.)
    y_motor : object
        any 'setable' object (motor, temp controller, etc.)
    x_range : float
        x range of spiral
    y_range : float
        y range of spiral
    dr : float
        delta radius
    factor : float, optional
        radius gets divided by this
    time : float, optional
        applied to any detectors that have a `count_time` setting
    per_step : callable, optional
        hook for cutomizing action of inner loop (messages per step)
        See docstring of bluesky.plans.one_nd_step (the default) for
        details.
    md : dict, optional
        metadata
    '''
    px, py = scan_patterns.spiral_fermat(x_range, y_range, dr, factor)

    cyc = cycler(x_motor, px)
    cyc += cycler(y_motor, py)

    total_points = len(cyc)

    plan_stack = deque()
    plan_stack.append(_pre_scan(total_points=total_points))

    gs = get_gs()
    subs = {'all': [LiveTable([x_motor, y_motor, gs.PLOT_Y] + gs.TABLE_COLS),
                    spec_api.setup_plot([x_motor]),
                    ]}

    with plans.subs_context(plan_stack, subs):
        plan = plans.scan_nd(gs.DETS, cyc, per_step=per_step, md=md)
        plan = plans.configure_count_time(plan, time)
        plan_stack.append(plan)
    return plan_stack


@plans.planify
def relative_fermat(x_motor, y_motor, x_range, y_range, dr, factor, time=None,
                    *, per_step=None, md=None):
    '''Relative fermat spiral scan

    Parameters
    ----------
    x_motor : object
        any 'setable' object (motor, temp controller, etc.)
    y_motor : object
        any 'setable' object (motor, temp controller, etc.)
    x_range : float
        x range of spiral
    y_range : float
        y range of spiral
    dr : float
        delta radius
    factor : float, optional
        radius gets divided by this
    time : float, optional
        applied to any detectors that have a `count_time` setting
    per_step : callable, optional
        hook for cutomizing action of inner loop (messages per step)
        See docstring of bluesky.plans.one_nd_step (the default) for
        details.
    md : dict, optional
        metadata
    '''
    plan = absolute_fermat(x_motor, y_motor, x_range, y_range, dr, factor,
                           time=time, per_step=per_step, md=md)
    plan = plans.relative_set(plan)  # re-write trajectory as relative
    plan = plans.reset_positions(plan)  # return motors to starting pos
    return [plan]


# class HxnInnerAbsScan(HxnScanMixin1D, plans.InnerProductAbsScanPlan):
#     pass
#
#
# class HxnInnerDeltaScan(HxnScanMixin1D, plans.InnerProductDeltaScanPlan):
#     pass
#
#
# class HxnScanMixinOuter:
#     def _gen(self):
#         # bluesky increments the scan id by one in open_run,
#         # so set it appropriately
#         gs.RE.md['scan_id'] = get_next_scan_id() - 1
#
#         total_points = 1
#         for motor, start, stop, num, snake in chunked(self.args, 5):
#             total_points *= num
#
#         if hasattr(self, '_pre_scan_calculate'):
#             yield from self._pre_scan_calculate()
#
#         yield from scan_setup(self.detectors, total_points=total_points)
#         yield from super()._gen()
#
#
# class HxnOuterAbsScan(HxnScanMixinOuter, plans.OuterProductAbsScanPlan):
#     pass
