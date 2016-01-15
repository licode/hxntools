import logging

from boltons.iterutils import chunked
from bluesky.run_engine import Msg
from bluesky import (plans, simple_scans)
from bluesky.standard_config import gs
from ophyd.controls import EpicsSignal
from ophyd.controls.positioner import Positioner


logger = logging.getLogger(__name__)


scaler1_output_mode = EpicsSignal('XF:03IDC-ES{Sclr:1}OutputMode',
                                  name='scaler1_output_mode')
scaler1_stopall = EpicsSignal('XF:03IDC-ES{Sclr:1}StopAll',
                              name='scaler1_stopall')

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


def check_scaler():
    if scaler1_output_mode.get(as_string=True) != 'Mode 1':
        logger.info('Setting scaler 1 to output mode 1')
        scaler1_output_mode.put('Mode 1')

    # Ensure that the scaler isn't counting in mcs mode for any reason
    scaler1_stopall.put(1)


def scan_setup(detectors, total_points):
    check_scaler()
    for det in detectors:
        if not hasattr(det, 'set'):
            continue

        if isinstance(det, (EpicsSignal, Positioner)):
            logger.debug('Skipping detector %s', det)
            continue
        logger.debug('Setting up detector %s', det)
        yield Msg('set', det, scan_mode='step_scan', total_points=total_points)


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
