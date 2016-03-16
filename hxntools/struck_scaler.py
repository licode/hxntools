import collections
from ophyd import (EpicsScaler, Device,
                   Component as Cpt, DynamicDeviceComponent as DDC,
                   EpicsSignal, EpicsSignalRO, Signal)
from ophyd.mca import EpicsMCARecord
from .detectors.trigger_mixins import HxnModalBase


class MinimalCalcRecord(Device):
    value = Cpt(EpicsSignal, '.VAL')
    equation = Cpt(EpicsSignal, '.CALC$', string=True)


def _scaler_calc_records(suffix_format='', range_=None):
    if range_ is None:
        range_ = range(1, 9)

    recs = collections.OrderedDict()

    for i in range_:
        attr = 'calc{}'.format(i)
        recs[attr] = (MinimalCalcRecord, suffix_format.format(i), {})

    return recs


class StruckMCA(EpicsMCARecord):
    def __init__(self, prefix, *, index=None, **kwargs):
        self.index = index
        super().__init__(prefix, **kwargs)

    def stop(self):
        pass


def _struck_mca_records(prefix_format, range_):
    recs = collections.OrderedDict()

    for i in range_:
        attr = 'mca{:02d}'.format(i)
        mca_prefix = prefix_format.format(i)
        recs[attr] = (StruckMCA, mca_prefix, dict(index=i))

    recs['mca_attrs'] = (Signal, None, dict(value=tuple(recs.keys())))
    return recs


class EpicsScalerWithCalc(EpicsScaler):
    calculations = DDC(_scaler_calc_records('_calc{}', range(1, 9)))
    enable_calculations = Cpt(EpicsSignal, '_calcEnable')


class StruckScaler(EpicsScalerWithCalc):
    mca_count = 32

    mcas = DDC(_struck_mca_records('Mca:{}', range(1, mca_count + 1)))

    acquire_mode = Cpt(EpicsSignal, 'AcquireMode')
    acquiring = Cpt(EpicsSignal, 'Acquiring')
    asyn = Cpt(EpicsSignal, 'Asyn')
    channel1_source = Cpt(EpicsSignal, 'Channel1Source')
    channel_advance = Cpt(EpicsSignal, 'ChannelAdvance')
    client_wait = Cpt(EpicsSignal, 'ClientWait')
    count_on_start = Cpt(EpicsSignal, 'CountOnStart')
    current_channel = Cpt(EpicsSignal, 'CurrentChannel')
    disable_auto_count = Cpt(EpicsSignal, 'DisableAutoCount')
    do_read_all = Cpt(EpicsSignal, 'DoReadAll')
    dwell = Cpt(EpicsSignal, 'Dwell')
    elapsed_real = Cpt(EpicsSignal, 'ElapsedReal')
    enable_client_wait = Cpt(EpicsSignal, 'EnableClientWait')
    erase_all = Cpt(EpicsSignal, 'EraseAll')
    erase_start = Cpt(EpicsSignal, 'EraseStart')
    firmware = Cpt(EpicsSignal, 'Firmware')
    hardware_acquiring = Cpt(EpicsSignal, 'HardwareAcquiring')
    input_mode = Cpt(EpicsSignal, 'InputMode')
    max_channels = Cpt(EpicsSignal, 'MaxChannels')
    model = Cpt(EpicsSignal, 'Model')
    mux_output = Cpt(EpicsSignal, 'MUXOutput')
    nuse_all = Cpt(EpicsSignal, 'NuseAll')
    output_mode = Cpt(EpicsSignal, 'OutputMode')
    output_polarity = Cpt(EpicsSignal, 'OutputPolarity')
    prescale = Cpt(EpicsSignal, 'Prescale')
    preset_real = Cpt(EpicsSignal, 'PresetReal')
    read_all = Cpt(EpicsSignal, 'ReadAll')
    read_all_once = Cpt(EpicsSignal, 'ReadAllOnce')
    set_acquiring = Cpt(EpicsSignal, 'SetAcquiring')
    set_client_wait = Cpt(EpicsSignal, 'SetClientWait')
    snl_connected = Cpt(EpicsSignal, 'SNL_Connected')
    software_channel_advance = Cpt(EpicsSignal, 'SoftwareChannelAdvance')
    start_all = Cpt(EpicsSignal, 'StartAll')
    stop_all = Cpt(EpicsSignal, 'StopAll')
    user_led = Cpt(EpicsSignal, 'UserLED')
    wfrm = Cpt(EpicsSignal, 'Wfrm')

    def __init__(self, prefix, **kwargs):
        super().__init__(prefix, **kwargs)

        mca_attrs = self.mcas.mca_attrs.get()
        self.mca_by_index = {getattr(self.mcas, attr).index: getattr(self.mcas,
                                                                     attr)
                             for attr in mca_attrs}


class HxnTriggeringScaler(HxnModalBase, StruckScaler):
    def __init__(self, prefix, *, scan_type_triggers=None, **kwargs):
        super().__init__(prefix, **kwargs)

        if scan_type_triggers is None:
            scan_type_triggers = {'step': [],
                                  'fly': [],
                                  }

        self.scan_type_triggers = dict(scan_type_triggers)

        # Scaler 1 should be in output mode 1 to properly trigger
        self.stage_sigs[self.output_mode] = 'Mode 1'
        # Ensure that the scaler isn't counting in mcs mode for any reason
        self.stage_sigs[self.stop_all] = 1

    def mode_internal(self):
        settings = self.mode_settings
        triggers = self.scan_type_triggers[settings.scan_type]
        settings.triggers.put(list(triggers))

    def trigger_internal(self):
        return EpicsScaler.trigger(self)

    def trigger_external(self):
        raise NotImplementedError()


class HxnScaler(StruckScaler):
    pass
