import collections
import numpy as np
from databroker import DataBroker as db
import logging


logger = logging.getLogger(__name__)


def _eval(scan_args):
    '''Evaluate scan arguments, replacing OphydObjects with NamedObjects'''

    class NamedObject:
        def __init__(self, name):
            self.name = name

    def no_op():
        def no_op_inner(*args, name=None, **kwargs):
            if name is not None:
                return NamedObject(name)

        return no_op_inner

    return eval(scan_args, collections.defaultdict(no_op))


scan_types = dict(
    v0=dict(step_1d=('InnerProductAbsScan', 'HxnInnerAbsScan',
                     'InnerProductDeltaScan', 'HxnInnerDeltaScan', 'AbsScan',
                     'HxnAbsScan', 'DeltaScan', 'HxnDeltaScan'),
            step_2d=('OuterProductAbsScan', 'HxnOuterAbsScan', 'relative_mesh',
                     'absolute_mesh'),
            spiral=('HxnFermatPlan', 'relative_fermat', 'absolute_fermat',
                    'relative_spiral', 'absolute_spiral'),
            fly=('FlyPlan1D', 'FlyPlan2D'),
            ),
    v1=dict(step_1d=('relative_scan', 'absolute_scan', 'count'),
            step_2d=('relative_mesh', 'absolute_mesh'),
            spiral=('spiral_fermat', 'relative_spiral_fermat',
                    'spiral', 'relative_spiral', ),
            fly=('FlyPlan1D', 'FlyPlan2D'),
            ),
)



def _get_scan_info_bs_v0(header):
    info = {'num': 0,
            'dimensions': [],
            'motors': [],
            'range': [],
            'pyramid': False,
            }

    start_doc = header['start']
    try:
        scan_args = start_doc['scan_args']
    except KeyError:
        try:
            scan_args = start_doc['plan_args']
        except KeyError:
            logger.error('No scan args for scan %s', start_doc['uid'])
            return info

    try:
        scan_type = start_doc['scan_type']
    except KeyError:
        try:
            scan_type = start_doc['plan_type']
        except KeyError:
            logger.error('No plan type for scan %s', start_doc['uid'])
            return info

    motors = None
    range_ = None
    pyramid = False
    motor_keys = None
    dimensions = []

    scan_type_info = scan_types['v0']
    step_1d = scan_type_info['step_1d']
    step_2d = scan_type_info['step_2d']
    spiral_scans = scan_type_info['spiral']
    fly_scans = scan_type_info['fly']

    if scan_type in fly_scans:
        logger.debug('Scan %s (%s) is a fly scan (%s)', start_doc.scan_id,
                     start_doc.uid, scan_type)
        dimensions = start_doc['dimensions']
        try:
            motors = start_doc['motors']
        except KeyError:
            motors = start_doc['axes']

        pyramid = start_doc['fly_type'] == 'pyramid'
        try:
            range_ = start_doc['scan_range']
        except KeyError:
            try:
                range_ = [(float(start_doc['scan_start']),
                           float(start_doc['scan_end']))]
            except (KeyError, ValueError):
                pass
    elif scan_type in step_2d:
        logger.debug('Scan %s (%s) is an ND scan (%s)', start_doc.scan_id,
                     start_doc.uid, scan_type)

        try:
            args = _eval(scan_args['args'])
        except Exception:
            pass

        # 2D mesh scan
        try:
            motors = [arg.name for arg in args[::5]]
        except Exception:
            motors = []

        try:
            dimensions = args[3::5]
            range0 = args[1::5]
            range1 = args[2::5]
            range_ = list(zip(range0, range1))
        except Exception:
            dimensions = []
            range_ = []

    elif scan_type in spiral_scans:
        motor_keys = ['x_motor', 'y_motor']
        dimensions = [int(start_doc['num'])]
        logger.debug('Scan %s (%s) is a fermat scan (%s) %d points',
                     start_doc.scan_id, start_doc.uid, scan_type,
                     dimensions[0])
        try:
            range_ = [(float(start_doc['x_range']),
                       float(start_doc['y_range']))]
        except (KeyError, ValueError):
            pass

    elif scan_type in step_1d or 'num' in start_doc:
        logger.debug('Scan %s (%s) is a 1D scan (%s)', start_doc.scan_id,
                     start_doc.uid, scan_type)
        # 1D scans
        try:
            dimensions = [int(start_doc['num'])]
        except KeyError:
            # some scans with the bluesky md changes didn't save num
            dimensions = []
        motor_keys = ['motor']
    else:
        msg = 'Unrecognized scan type (uid={} {})'.format(start_doc.uid,
                                                          scan_type)
        raise RuntimeError(msg)

    if motor_keys:
        motors = []
        for key in motor_keys:
            try:
                motors.append(_eval(start_doc[key]).name)
            except Exception:
                pass

    num = np.product(dimensions)

    info['num'] = num
    info['dimensions'] = dimensions
    info['motors'] = motors
    info['range'] = range_
    info['pyramid'] = pyramid
    return info


def get_scan_info(header):
    start_doc = header['start']
    if 'scan_args' in start_doc:
        return _get_scan_info_bs_v0(header)
    elif 'plan_args' in start_doc:
        return _get_scan_info_bs_v1(header)
    else:
        raise RuntimeError('Unknown start document information')


def _get_scan_info_bs_v1(header):
    start_doc = header['start']
    info = {'num': 0,
            'dimensions': [],
            'motors': [],
            'range': [],
            'pyramid': False,
            }

    plan_args = start_doc['plan_args']
    plan_type = start_doc['plan_type']
    plan_name = start_doc['plan_name']

    motors = None
    range_ = None
    pyramid = False
    dimensions = []

    plan_type_info = scan_types['v1']
    step_1d = plan_type_info['step_1d']
    step_2d = plan_type_info['step_2d']
    spiral_scans = plan_type_info['spiral']
    fly_scans = plan_type_info['fly']

    motors = start_doc['motors']

    if plan_type in fly_scans:
        logger.debug('Scan %s (%s) is a fly scan (%s %s)', start_doc.scan_id,
                     start_doc.uid, plan_type, plan_name)
        dimensions = start_doc['dimensions']
        pyramid = start_doc['fly_type'] == 'pyramid'
        range_ = start_doc['scan_range']
    elif plan_name in step_2d:
        logger.debug('Scan %s (%s) is an ND scan (%s %s)', start_doc.scan_id,
                     start_doc.uid, plan_type, plan_name)

        args = plan_args['args']
        range0 = args[1::5]
        range1 = args[2::5]
        range_ = list(zip(range0, range1))
        dimensions = args[3::5]
    elif plan_name in spiral_scans:
        # TODO insert 'num' in
        dimensions = [int(start_doc['num_step'])]
        logger.debug('Scan %s (%s) is a spiral scan (%s %s) %d points',
                     start_doc.scan_id, start_doc.uid, plan_type,
                     plan_name, dimensions[0])
        range_ = [plan_args['x_range'], plan_args['y_range']]
    elif plan_name in step_1d or 'num' in start_doc:
        logger.debug('Scan %s (%s) is a 1D scan (%s %s)', start_doc.scan_id,
                     start_doc.uid, plan_type, plan_name)
        try:
            dimensions = [int(start_doc['num'])]
        except KeyError:
            # TODO
            dimensions = [1]
    else:
        msg = ('Unrecognized plan type/name (uid={} name={} type={})'
               ''.format(start_doc.uid, plan_name, plan_type))
        raise RuntimeError(msg)

    num = np.product(dimensions)
    info['num'] = num
    info['dimensions'] = dimensions
    info['motors'] = motors
    info['range'] = range_
    info['pyramid'] = pyramid
    return info


class ScanInfo(object):
    def __init__(self, header):
        self.header = header
        self.start_doc = header['start']
        self.descriptors = header['descriptors']
        self.key = None
        for key, value in get_scan_info(self.header).items():
            logger.debug('Scan info %s=%s', key, value)
            setattr(self, key, value)

    @property
    def filestore_keys(self):
        for desc in self.descriptors:
            for key, info in desc['data_keys'].items():
                try:
                    external = info['external']
                except KeyError:
                    continue

                try:
                    source, info = external.split(':', 1)
                except Exception:
                    pass
                else:
                    source = source.lower()
                    if source in ('filestore', ):
                        yield key

    @property
    def scan_id(self):
        return self.start_doc['scan_id']

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, self.header)

    def __iter__(self):
        if self.key:
            for event in db.get_events(self.header, fill=False):
                yield event['data'][self.key]
