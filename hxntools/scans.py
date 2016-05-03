import asyncio
import functools
import ophyd
import logging

from boltons.iterutils import chunked
from bluesky import (plans, spec_api, Msg)
from bluesky.global_state import get_gs
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

    # TODO
    ophyd.Signal.set = ophyd.Signal.put


@functools.wraps(spec_api.ascan)
def ascan(motor, start, finish, intervals, time=None, **kwargs):
    gs = get_gs()
    yield Msg('hxn_next_scan_id')
    yield Msg('hxn_scan_setup', detectors=gs.DETS, total_points=intervals + 1)
    yield from spec_api.ascan(motor, start, finish, intervals, time, **kwargs)


@functools.wraps(spec_api.dscan)
def dscan(motor, start, finish, intervals, time=None, **kwargs):
    gs = get_gs()
    yield Msg('hxn_next_scan_id')
    yield Msg('hxn_scan_setup', detectors=gs.DETS, total_points=intervals + 1)
    yield from spec_api.dscan(motor, start, finish, intervals, time, **kwargs)

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
