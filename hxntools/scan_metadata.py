from __future__ import print_function
import logging
import getpass

from IPython import get_ipython


ip = get_ipython()
logger = logging.getLogger(__name__)


def get_scan_owner():
    owner = ip.user_ns.get('scan_owner', None)
    if not isinstance(owner, str):
        owner = getpass.getuser()
        logger.warning('Variable `scan_owner` unset or invalid. Specify a '
                       'string to identify this scan to a particular user. '
                       'Defaulting to: %s', owner)
        return owner

    return owner


def get_user_project_info():
    ret = ip.user_ns.get('project_info', None)
    if not isinstance(ret, (dict, str)):
        logger.warning('Variable `project_info` must be a dictionary or a '
                       'string to be stored with the scan information '
                       'header')
        return None

    return ret


def get_user_scan_metadata():
    try:
        ret = ip.user_ns['scan_metadata']
    except KeyError:
        logger.warning('Variable `scan_metadata` unset. Set this to a '
                       'dictionary to store metadata with the scan '
                       'information header.')
        ret = {}

    if not isinstance(ret, (dict, )):
        logger.warning('Variable `scan_metadata` must be a dictionary '
                       'be stored with the scan information header')
        return {}

    return ret


def get_beamline_config(key='beamline_config_pvs'):
    try:
        signals = ip.user_ns[key]
    except KeyError:
        logger.warning('Variable `%s` unset. Make this a list of signals '
                       'to store at the start of each scan', key)
        return {}

    return {signal.name: signal.get()
            for signal in signals}
