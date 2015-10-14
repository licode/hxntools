import logging

from boltons.iterutils import chunked
from bluesky.run_engine import Msg
from bluesky import (scans, simple_scans)
from ophyd.controls import EpicsSignal
from ophyd.controls.positioner import Positioner


logger = logging.getLogger(__name__)


scaler1_output_mode = EpicsSignal('XF:03IDC-ES{Sclr:1}OutputMode',
                                  name='scaler1_output_mode')
scaler1_stopall = EpicsSignal('XF:03IDC-ES{Sclr:1}StopAll',
                              name='scaler1_stopall')


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
        yield from super()._pre_scan()
        yield from scan_setup(self.detectors, total_points=self.num)


class HxnAbsScan(HxnScanMixin1D, scans.AbsScan):
    pass


class HxnDeltaScan(HxnScanMixin1D, scans.DeltaScan):
    pass


class HxnInnerAbsScan(HxnScanMixin1D, scans.InnerProductAbsScan):
    pass


class HxnInnerDeltaScan(HxnScanMixin1D, scans.InnerProductDeltaScan):
    pass


class HxnScanMixinOuter:
    def _pre_scan(self):
        total_points = 1
        for motor, start, stop, num, snake in chunked(self.args, 5):
            total_points *= num

        yield from scan_setup(self.detectors, total_points=total_points)
        yield from super()._pre_scan()


class HxnOuterAbsScan(HxnScanMixinOuter, scans.OuterProductAbsScan):
    pass


def setup():
    simple_scans.AbsScan.scan_class = HxnAbsScan
    simple_scans.DeltaScan.scan_class = HxnDeltaScan
    simple_scans.InnerProductAbsScan.scan_class = HxnInnerAbsScan
    simple_scans.InnerProductDeltaScan.scan_class = HxnInnerDeltaScan
    simple_scans.OuterProductAbsScan.scan_class = HxnOuterAbsScan
