import logging
import numpy as np

from bluesky.run_engine import Msg
from bluesky import (scans, simple_scans)
from bluesky.simple_scans import (_BundledScan, _set_acquire_time,
                                  _unset_acquire_time)
from bluesky.utils import DefaultSubs
from .scans import HxnScanMixin1D
from .scan_patterns import spiral_fermat

from collections import defaultdict
from cycler import cycler

logger = logging.getLogger(__name__)


class MultipleMotorPlan(scans.ScanND):
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
    _fields = ['detectors', 'motors', 'point_args']

    def __init__(self, detectors, motors, point_args):
        self.detectors = detectors
        self._motors = list(motors)
        self.point_args = list(point_args)
        self.num = None

        # TODO ScanND overwrites this with cycler.keys...
        self.motors = list(motors)
        # TODO I'd like these to be reusable, but my other stuff relies on
        # the number of points being determined prior to pre-scan
        self.points = self.get_points(*self.point_args)
        self.num = len(self.points)

    def _pre_scan(self):
        points = self.points
        # points = self.get_points(*self.point_args)
        self.cycler = None
        for motor, m_points in zip(self._motors, points):
            m_points = np.asarray(m_points) + self._offsets[motor]
            c = cycler(motor, m_points)
            if self.cycler is None:
                self.cycler = c
            else:
                self.cycler += c

        self.num = len(self.cycler)
        yield from super()._pre_scan()

    def get_points(self, *args):
        '''
        Returns
        -------
        points : list of positions for each motor
            [(m1p1, m2p1, ...), ..., (m1pN, m2pN)]
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
    points : list of positions for each motor
        [(m1p1, m2p1, ...), ..., (m1pN, m2pN)]
        where m1p1 is motor 1, position 1
    """
    def _pre_scan(self):
        self._offsets = defaultdict(lambda: 0.0)
        yield from super()._pre_scan()


class MultipleMotorDeltaScan(MultipleMotorPlan):
    """Delta (relative) scan over multi-motor trajectory

    Parameters
    ----------
    detectors : list
        list of 'readable' objects
    motors : list of motors
        (m1, m2, ...)
    points : list of positions for each motor
        [(m1p1, m2p1, ...), ..., (m1pN, m2pN)]
        where m1p1 is motor 1, position 1
    """
    def _pre_scan(self):
        self._offsets = {}
        for motor in self.motors:
            ret = yield Msg('read', motor)
            current_value = ret[motor.name]['value']
            self._offsets[motor] = current_value
        yield from super()._pre_scan()

    def _post_scan(self):
        # Return the motor to its original position.
        yield from super()._post_scan()
        for motor in self.motors:
            yield Msg('set', motor, self._offsets[motor], block_group='A')
        yield Msg('wait', None, 'A')


class HxnFermatPlan(HxnScanMixin1D, MultipleMotorDeltaScan):
    """Relative fermat spiral scan

    Parameters
    ----------
    detectors : list
        list of 'readable' objects
    motorx : object
        any 'setable' object (motor, temp controller, etc.)
    motory : object
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

    def __init__(self, detectors, motor1, motor2, x_range, y_range, dr, factor,
                 **kwargs):

        motors = [motor1, motor2]
        point_args = [x_range, y_range, dr, factor]
        super().__init__(detectors, motors, point_args, **kwargs)

    def get_points(self, x_range, y_range, dr, factor):
        return spiral_fermat(x_range, y_range, dr, factor)


class HxnFermatScan(_BundledScan):
    """Relative fermat spiral scan

    Parameters
    ----------
    motorx : object
        any 'setable' object (motor, temp controller, etc.)
    motory : object
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
    scan_class = HxnFermatPlan

    def __call__(self, motor1, motor2, x_range, y_range, dr, factor, time=None,
                 **kwargs):
        original_times = _set_acquire_time(time)
        result = super().__call__(motor1, motor2, x_range, y_range, dr, factor,
                                  **kwargs)
        _unset_acquire_time(original_times)
        return result
