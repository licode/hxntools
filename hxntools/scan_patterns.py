import numpy as np


def spiral_simple(x_range_egu, y_range_egu, dr_egu, nth):
    """
    Spiral scan pattern 1

    Parameters
    ----------
    x_range_egu : float
        X range, in engineering units
    y_range_egu : float
        Y range, in engineering units
    dr_egu : float
        Delta radius, in engineering units
    nth : float
        Number of theta steps
    """
    r_max_egu = np.sqrt((x_range_egu / 2.) ** 2 + (y_range_egu / 2.) ** 2)
    num_ring = 1 + int(r_max_egu / dr_egu)

    half_x = x_range_egu / 2
    half_y = y_range_egu / 2

    x_points = []
    y_points = []
    for i_ring in range(1, num_ring + 2):
        radius_egu = i_ring * dr_egu
        angle_step = 2. * np.pi / (i_ring * nth)

        for i_angle in range(int(i_ring * nth)):
            angle = i_angle * angle_step
            x_egu = radius_egu * np.cos(angle)
            y_egu = radius_egu * np.sin(angle)
            if abs(x_egu) <= half_x and abs(y_egu) <= half_y:
                x_points.append(x_egu)
                y_points.append(y_egu)

    return x_points, y_points


def spiral_fermat(x_range_egu, y_range_egu, dr_egu, factor):
    """Fermat spiral scan pattern

    Parameters
    ----------
    x_range_egu : float
        X range, in engineering units
    y_range_egu : float
        Y range, in engineering units
    dr_egu : float
        Delta radius, in engineering units
    factor : float
        Radius divided by this factor
    """
    phi = 137.508 * np.pi / 180.

    half_x = x_range_egu / 2
    half_y = y_range_egu / 2

    x_points, y_points = [], []

    diag = np.sqrt(x_range_egu ** 2 + y_range_egu ** 2)
    num_rings = int((1.5 * diag * factor / dr_egu) ** 2)
    for i_ring in range(1, num_rings):
        radius_egu = np.sqrt(i_ring) * dr_egu / factor
        angle = phi * i_ring
        x_egu = radius_egu * np.cos(angle)
        y_egu = radius_egu * np.sin(angle)

        if abs(x_egu) <= half_x and abs(y_egu) <= half_y:
            x_points.append(x_egu)
            y_points.append(y_egu)

    return x_points, y_points
