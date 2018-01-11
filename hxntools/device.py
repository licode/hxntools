from ophyd import Device


def rename_device(dev, device_name, *,
                  special_attributes=None):
    '''Rename a device

    Parameters
    ----------
    dev : Device
    device_name : str
    special_attributes : str, optional
        If the attribute name matches any of these, the component instance
        will be named the same as the device.
        Defaults to ('readback', 'user_readback')
    '''
    dev.name = device_name

    if special_attributes is None:
        special_attributes = ('readback', 'user_readback')

    cls = dev.__class__
    for attribute in dev.component_names:
        obj = getattr(dev, attribute)
        component_cls = getattr(cls, attribute)

        if attribute in special_attributes:
            new_name = device_name
        else:
            new_name = component_cls.kwargs.get('name', attribute)
            new_name = '{}_{}'.format(device_name, new_name)

        obj.name = new_name

        if isinstance(obj, Device):
            rename_device(obj, new_name)


def rename_sub_devices(dev, *, special_attributes=None):
    '''Rename all sub-devices according to their keyword argument names'''
    cls = dev.__class__

    for attribute in dev.component_names:
        obj = getattr(dev, attribute)
        component_cls = getattr(cls, attribute)
        new_name = component_cls.kwargs.get('name', attribute)

        obj.name = new_name
        if isinstance(obj, Device):
            rename_device(obj, new_name,
                          special_attributes=special_attributes)


class NamedDevice(Device):
    '''
    NamedDevice will name components exactly as the 'name' argument
    specifies. Normally, it would be named based on the parent
    device's name: {parent_name}_{component_attribute_name}

    ''' + Device.__doc__

    def __init__(self, prefix, **kwargs):
        super().__init__(prefix, **kwargs)

        rename_sub_devices(self)
