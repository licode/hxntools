from __future__ import print_function
import epics
import time


def shutter_open():
    open_pv = epics.PV('XF:03IDB-PPS{PSh}Cmd:Opn-Cmd')
    closed_pv = epics.PV('XF:03IDB-PPS{PSh}Sts:Cls-Sts')

    if closed_pv.get() != 0:
        print('Opening the photon shutter...')
        open_pv.put(1, wait=True)
        while closed_pv.get() == 0:
            print('Waiting for the shutter to open...')
            time.sleep(1.0)


def shutter_close():
    print('Closing the photon shutter...')
    close_pv = epics.PV('XF:03IDB-PPS{PSh}Cmd:Cls-Cmd')
    close_pv.put(1)
