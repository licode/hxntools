import logging

from boltons.iterutils import chunked
from bluesky import (plans, simple_scans)
from bluesky.standard_config import gs
from ophyd import EpicsSignal
from .detectors.trigger_mixins import HxnModalBase


logger = logging.getLogger(__name__)


next_scan_id_proc = EpicsSignal('XF:03IDC-ES{Status}NextScanID-Cmd.PROC',
                                name='next_scan_id_proc')
scan_id = EpicsSignal('XF:03IDC-ES{Status}ScanID-I',
                      name='scan_id')


def get_next_scan_id():
    last_id = int(scan_id.get(use_monitor=False))
    next_scan_id_proc.put(1, wait=True)

    new_id = int(scan_id.get(use_monitor=False))
    if last_id == new_id:
        raise RuntimeError('Scan ID unchanged. Check hxnutil IOC.')
    return new_id


def scan_setup(detectors, total_points):
    modal_dets = [det for det in detectors
                  if isinstance(det, HxnModalBase)]

    for det in detectors:
        logger.debug('Setting up detector %s', det)
        settings = det.mode_settings

        # start by using internal triggering
        mode = 'internal'
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

    mode = 'external'
    for det in detectors:
        det.mode_settings.mode.put(mode)
        det.mode_setup(mode)


class HxnScanMixin1D:
    def _pre_scan(self):
        # bluesky increments the scan id by one in open_run,
        # so set it appropriately
        gs.RE.md['scan_id'] = get_next_scan_id() - 1
        if hasattr(self, '_pre_scan_calculate'):
            yield from self._pre_scan_calculate()
        yield from scan_setup(self.detectors, total_points=self.num)
        yield from super()._pre_scan()


class HxnAbsScan(HxnScanMixin1D, plans.AbsScanPlan):
    pass


class HxnDeltaScan(HxnScanMixin1D, plans.DeltaScanPlan):
    pass


class HxnInnerAbsScan(HxnScanMixin1D, plans.InnerProductAbsScanPlan):
    pass


class HxnInnerDeltaScan(HxnScanMixin1D, plans.InnerProductDeltaScanPlan):
    pass


class HxnScanMixinOuter:
    def _pre_scan(self):
        # bluesky increments the scan id by one in open_run,
        # so set it appropriately
        gs.RE.md['scan_id'] = get_next_scan_id() - 1

        total_points = 1
        for motor, start, stop, num, snake in chunked(self.args, 5):
            total_points *= num

        if hasattr(self, '_pre_scan_calculate'):
            yield from self._pre_scan_calculate()

        yield from scan_setup(self.detectors, total_points=total_points)
        yield from super()._pre_scan()


class HxnOuterAbsScan(HxnScanMixinOuter, plans.OuterProductAbsScanPlan):
    pass


def setup():
    simple_scans.AbsScan.plan_class = HxnAbsScan
    simple_scans.DeltaScan.plan_class = HxnDeltaScan
    simple_scans.InnerProductAbsScan.plan_class = HxnInnerAbsScan
    simple_scans.InnerProductDeltaScan.plan_class = HxnInnerDeltaScan
    simple_scans.OuterProductAbsScan.plan_class = HxnOuterAbsScan
