class HxnScanNumberPrinter:
    def __init__(self):
        self._last_start = None

    def __call__(self, name, doc):
        if name == 'start':
            self._last_start = doc
        if self._last_start is None:
            return
        if name in ('start', 'stop'):
            print('Scan ID: {scan_id} [{uid}]'.format(**self._last_start))
