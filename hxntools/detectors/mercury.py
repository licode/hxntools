from ophyd import (Component as Cpt)
from ophyd.mca import (MercuryDXP, EpicsMCARecord, EpicsDXPMultiElementSystem,
                       SoftDXPTrigger)


class HxnMercuryDetector(SoftDXPTrigger, EpicsDXPMultiElementSystem):
    '''DXP Mercury with 1 channel example'''
    dxp = Cpt(MercuryDXP, 'dxp1:')
    mca = Cpt(EpicsMCARecord, 'mca1')
