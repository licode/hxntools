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


step_1d = ('InnerProductAbsScan', 'HxnInnerAbsScan',
           'InnerProductDeltaScan', 'HxnInnerDeltaScan',
           'AbsScan', 'HxnAbsScan',
           'DeltaScan', 'HxnDeltaScan')

step_2d = ('OuterProductAbsScan', 'HxnOuterAbsScan')
fermat_scans = ('HxnFermatPlan', )
fly_scans = ('FlyPlan1D', 'FlyPlan2D')


def get_scan_info(header):
    # TODO some of this can/should be redone with the new metadatastore
    # fields (derived and otherwise)
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
        logger.error('No scan args for scan %s', start_doc['uid'])
        return info

    scan_type = start_doc['scan_type']
    motors = None
    range_ = None
    pyramid = False
    motor_keys = None
    exposure_time = 0.0
    dimensions = []

    if scan_type in fly_scans:
        dimensions = start_doc['dimensions']
        motors = start_doc['axes']
        pyramid = start_doc['fly_type'] == 'pyramid'
        exposure_time = float(scan_args.get('exposure_time', 0.0))

        logger.debug('Scan %s (%s) is a fly-scan (%s) of axes %s '
                     'with per-frame exposure time of %.3f s',
                     start_doc.scan_id, start_doc.uid, scan_type,
                     motors, exposure_time)
        try:
            range_ = start_doc['scan_range']
        except KeyError:
            try:
                range_ = [(float(scan_args['scan_start']),
                           float(scan_args['scan_end']))]
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

    elif scan_type in fermat_scans:
        motor_keys = ['x_motor', 'y_motor']
        dimensions = [int(start_doc['num'])]
        exposure_time = float(scan_args.get('exposure_time', 0.0))
        logger.debug('Scan %s (%s) is a fermat scan (%s) %d points, '
                     'with per-point exposure time of %.3f s',
                     start_doc.scan_id, start_doc.uid, scan_type,
                     dimensions[0], exposure_time)
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
    info['exposure_time'] = exposure_time
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
            for event in db.fetch_events(self.header, fill=False):
                yield event['data'][self.key]
