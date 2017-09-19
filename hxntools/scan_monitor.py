import logging

import time

# from ophyd import EpicsSignal
from epics import PV
from bluesky.utils import CallbackRegistry

from .scan_info import get_scan_info


logger = logging.getLogger(__name__)


class ScanUidMonitor:
    '''Monitor scans via uid PV

    Callback signature looks like:
    * 'start': scan_started(uid)
    * 'stop': scan_finished(uid)

    Parameters
    ----------
    uid_pv : str
        The UID PV name
    '''
    def __init__(self, uid_pv, db):
        self.last_uid = None
        self.cb_registry = CallbackRegistry(allowed_sigs=('start', 'stop'))

        self.cb_registry.connect('start', self.scan_started)
        self.cb_registry.connect('stop', self.scan_finished)

        self.uid_pv = PV(uid_pv, callback=self._uid_changed)
        self.db = db

    def connect(self, sig, func):
        """Register ``func`` to be called when ``sig`` is generated

        Parameters
        ----------
        sig : 'start' or 'stop'
            The signal to monitor
        func : callable
            The function to call

        Returns
        -------
        cid : int
            The callback index. To be used with ``disconnect`` to deregister
            ``func`` so that it will no longer be called when ``sig`` is
            generated
        """
        self.cb_registry.connect(sig, func)

    def disconnect(self, cid):
        """Disconnect the callback registered with callback id *cid*

        Parameters
        ----------
        cid : int
            The callback index and return value from ``connect``
        """
        self.cb_registry.disconnect(cid)

    def _uid_changed(self, value=None, **kwargs):
        '''Uid changed callback'''

        if not value:
            return

        if value != self.last_uid:
            if self.last_uid is not None:
                self._scan_finished(self.last_uid)

            self.last_uid = value
            self._scan_started(value)
        else:
            self._scan_finished(value)

    def _scan_started(self, uid):
        '''Scan started callback, according to uid'''
        logger.debug('Scan started: %s', uid)
        self.cb_registry.process('start', uid)

    def _scan_finished(self, uid):
        '''Scan finished callback, according to uid'''
        logger.debug('Scan finished: %s', uid)
        self.cb_registry.process('stop', uid)

    def scan_started(self, uid, **kwargs):
        '''Default scan started callback

        You can either use the callback registry or for single-use, just
        inherit from this class and override this function.
        '''
        pass

    def scan_finished(self, uid, **kwargs):
        '''Default scan finished callback

        You can either use the callback registry or for single-use, just
        inherit from this class and override this function.
        '''
        pass

    def run():
        print('Monitoring, press Ctrl-C to quit')
        try:
            while True:
                time.sleep(1.)
        except KeyboardInterrupt:
            pass



class ScanBrokerMonitor(ScanUidMonitor):
    '''Monitor scans via uid PV and retrieve metadatastore info

    Callback signature looks like:
    * 'start': scan_started(uid, start=None, **header)
    * 'stop': scan_finished(uid, start=None, stop=None, **header)

    Parameters
    ----------
    uid_pv : str
        The UID PV name
    '''

    def _get_additional_info(self, uid, signal, header):
        '''Additional kwargs for the callbacks'''
        return {}

    def _get_kwargs(self, uid, signal, header):
        '''Add in additional kwargs from _get_additional_info'''
        kwargs = dict(header)
        kwargs.update(self._get_additional_info(uid, signal, header))
        return kwargs

    def _query_db(self, uid):
        '''Query the databroker for a specific uid'''
        return self.db[uid]

    def _scan_started(self, uid):
        logger.debug('Scan started: %s', uid)

        header = self._query_db(uid)
        if header is None:
            return

        if header.get('stop', None) is not None:
            # scan already completed
            logger.debug('scan_started callback but scan is already done')
            self.last_uid = None
            kwargs = self._get_kwargs(uid, 'stop', header)
            self.cb_registry.process('stop', uid, **kwargs)
        else:
            kwargs = self._get_kwargs(uid, 'start', header)
            self.cb_registry.process('start', uid, **kwargs)

    def _scan_finished(self, uid):
        logger.debug('Scan finished: %s', uid)
        header = self._query_db(uid)
        if header is None:
            return
        kwargs = self._get_kwargs(uid, 'stop', header)
        self.cb_registry.process('stop', uid, **kwargs)

    def scan_started(self, uid, start=None, **header):
        pass

    def scan_finished(self, uid, start=None, stop=None, **header):
        pass


class HxnScanMonitor(ScanBrokerMonitor):
    '''Monitor scans via uid PV, retrieve mds info, and get hxn-specific info

    Callback signature looks like:
    * 'start': scan_started(uid, start={}, hxn_info={}, **header)
    * 'stop': scan_finished(uid, start={}, stop={}, hxn_info={}, **header)

    Parameters
    ----------
    uid_pv : str
        The UID PV name
    '''

    def _get_additional_info(self, uid, signal, header):
        return {'hxn_info': get_scan_info(header)}

    def scan_started(self, uid, start=None, hxn_info=None,
                     **header):
        pass

    def scan_finished(self, uid, start=None, stop=None, hxn_info=None,
                      **header):
        pass


def _test(db):
    import sys

    try:
        uid_pv = sys.argv[1]
    except IndexError:
        uid_pv = 'XF:03IDC-ES{BS-Scan}UID-I'

    print('Using uid pv: {}'.format(uid_pv))
    # uid_mon = ScanUidMonitor(uid_pv)
    # broker_mon = ScanBrokerMonitor(uid_pv)
    hxn_mon = HxnScanMonitor(uid_pv, db)

    hxn_mon.run()


if __name__ == '__main__':
    from databroker.databroker import DataBroker
    logging.basicConfig(level=logging.DEBUG)
    _test(DataBroker)
