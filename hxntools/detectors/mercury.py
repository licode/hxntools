from ophyd import (Component as Cpt, Device, EpicsSignal, EpicsSignalRO,
                   EpicsSignalWithRBV, DeviceStatus)
from ophyd.device import (BlueskyInterface, Staged)
from ophyd.mca import (MercuryDXP, EpicsMCARecord, EpicsDXPMultiElementSystem,
                       SoftDXPTrigger)


class HxnMercuryDetector(SoftDXPTrigger, EpicsDXPMultiElementSystem):
    '''DXP Mercury with 1 channel example'''
    dxp = Cpt(MercuryDXP, 'dxp1:')
    mca = Cpt(EpicsMCARecord, 'mca1')
