import asyncio
import logging
import numpy as np

from bluesky.run_engine import Msg
from bluesky import (plans, simple_scans)
from bluesky.simple_scans import (_BundledScan, _set_acquire_time,
                                  _unset_acquire_time)
from bluesky.utils import DefaultSubs
from .scans import HxnScanMixin1D
from .scan_patterns import spiral_fermat

from collections import defaultdict
from cycler import cycler

logger = logging.getLogger(__name__)


class MultipleMotorPlan(plans.PlanND):
    """Scan over multi-motor trajectory

    Parameters
    ----------
    detectors : list
        list of 'readable' objects
    motors : list of motors
        (m1, m2, ...)
    point_args : list
        List of arguments used to generate the points for the scan
    """
    _fields = ['detectors', 'motors', 'point_args']

    def __init__(self, detectors, motors, point_args):
        self.detectors = detectors
        self.point_args = list(point_args)
        self.num = None

        self._motors = list(motors)
        # the (non-private) .motors attribute is used by subscriptions and
        # is eventually overwritten by the cycler list. since we want
        # to keep the ordering of motors as the user specified, we
        # keep it in _motors
        self.motors = list(motors)

    @asyncio.coroutine
    def _pre_scan_calculate(self):
        # Called by HxnScanMixin1D - if in _pre_scan instead,
        # the order of operations is wrong and num will be None
        # when detectors are configured.
        self.points = self.get_points(*self.point_args)

        self.cycler = None
        for motor, m_points in zip(self._motors, self.points):
            m_points = np.asarray(m_points) + self._offsets[motor]
            c = cycler(motor, m_points)
            if self.cycler is None:
                self.cycler = c
            else:
                self.cycler += c

        self.num = len(self.cycler)

    def get_points(self, *args):
        '''
        Returns
        -------
        points : list of positions for each motor
            [(m1p1, m1p1, ...), ..., (mNp1, mNpM)]
            where m1p1 is motor 1, position 1
        '''
        raise NotImplementedError('get_points should be implemented on the '
                                  'subclass')


class MultipleMotorAbsPlan(MultipleMotorPlan):
    """Absolute scan over multi-motor trajectory

    Parameters
    ----------
    detectors : list
        list of 'readable' objects
    motors : list of motors
        (m1, m2, ...)
    point_args : list
        List of arguments used to generate the points for the scan
    """
    @asyncio.coroutine
    def _pre_scan_calculate(self):
        self._offsets = defaultdict(lambda: 0.0)
        yield from super()._pre_scan_calculate()


class MultipleMotorDeltaPlan(MultipleMotorPlan):
    """Delta (relative) scan over multi-motor trajectory

    Parameters
    ----------
    detectors : list
        list of 'readable' objects
    motors : list of motors
        (m1, m2, ...)
    point_args : list
        List of arguments used to generate the points for the scan
    """
    @asyncio.coroutine
    def _pre_scan_calculate(self):
        self._offsets = {}
        for motor in self.motors:
            ret = yield Msg('read', motor)
            current_value = ret[motor.name]['value']
            self._offsets[motor] = current_value
        yield from super()._pre_scan_calculate()

    def _post_scan(self):
        # Return the motor to its original position.
        yield from super()._post_scan()
        for motor in self.motors:
            yield Msg('set', motor, self._offsets[motor], block_group='A')
        yield Msg('wait', None, 'A')


class HxnFermatPlan(HxnScanMixin1D, MultipleMotorDeltaPlan):
    """Relative fermat spiral scan

    Parameters
    ----------
    detectors : list
        list of 'readable' objects
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
    factor : float
        radius gets divided by this

    Examples
    --------

    >>> my_plan = HxnFermatPlan([det1, det2], motor1, motor2, 1., 1., .1, 10)
    >>> RE(my_plan)
    # Adjust a Parameter and run again.
    >>> my_plan.x_range = 2.0
    >>> RE(my_plan)
    """
    _fields = MultipleMotorPlan._fields + ['x_motor', 'y_motor', 'x_range',
                                           'y_range', 'dr', 'factor']

    def __init__(self, detectors, x_motor, y_motor, x_range, y_range, dr, factor,
                 **kwargs):

        motors = [x_motor, y_motor]
        point_args = [x_range, y_range, dr, factor]
        super().__init__(detectors, motors, point_args, **kwargs)
        self.setup_attrs()

        self.x_motor = x_motor
        self.y_motor = y_motor
        self.x_range = x_range
        self.y_range = y_range
        self.dr = dr
        self.factor = factor

    def get_points(self, x_range, y_range, dr, factor):
        return spiral_fermat(x_range, y_range, dr, factor)


class HxnFermatScan(_BundledScan):
    """Relative fermat spiral scan

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
    factor : float
        radius gets divided by this
    time : float, optional
        detector preset time to synchronize to

    Examples
    --------

    >>> fermat(motor1, motor2, 1.0, 1.0, 0.1, 10, time=0.1)
    """

    default_subs = DefaultSubs({})
    default_sub_factories = DefaultSubs({'all': [simple_scans.table_from_motors,
                                                 simple_scans.plot_first_motor]}
                                        )
    plan_class = HxnFermatPlan

    def __call__(self, motor1, motor2, x_range, y_range, dr, factor, time=None,
                 **kwargs):
        original_times = _set_acquire_time(time)
        result = super().__call__(motor1, motor2, x_range, y_range, dr, factor,
                                  **kwargs)
        _unset_acquire_time(original_times)
        return result
