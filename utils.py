"""Common utilities for the FMI Weather and Sensor integrations."""

import math
from datetime import date, datetime
from dateutil import tz
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.const import SUN_EVENT_SUNSET, SUN_EVENT_SUNRISE

try:
    from . import const
except ImportError:
    import const


class BoundingBox():
    def __init__(self, lat_min=None, lon_min=None,
                 lat_max=None, lon_max=None):
        self.lat_min = lat_min
        self.lon_min = lon_min
        self.lat_max = lat_max
        self.lon_max = lon_max


def get_bounding_box_covering_finland():
    """Bounding box to covert while Finland."""
    box = BoundingBox()
    box.lat_min = const.BOUNDING_BOX_LAT_MIN
    box.lon_min = const.BOUNDING_BOX_LONG_MIN
    box.lat_max = const.BOUNDING_BOX_LAT_MAX
    box.lon_max = const.BOUNDING_BOX_LONG_MAX

    return box


def get_bounding_box(latitude_in_degrees, longitude_in_degrees, half_side_in_km):
    """Calculate min and max coordinates for bounding box."""
    assert 0 < half_side_in_km
    assert -90.0 <= latitude_in_degrees <= 90.0
    assert -180.0 <= longitude_in_degrees <= 180.0

    lat = math.radians(latitude_in_degrees)
    lon = math.radians(longitude_in_degrees)

    radius = 6371
    # Radius of the parallel at given latitude
    parallel_radius = radius * math.cos(lat)

    lat_min = lat - half_side_in_km / radius
    lat_max = lat + half_side_in_km / radius
    lon_min = lon - half_side_in_km / parallel_radius
    lon_max = lon + half_side_in_km / parallel_radius
    rad2deg = math.degrees

    box = BoundingBox()
    box.lat_min = rad2deg(lat_min)
    box.lon_min = rad2deg(lon_min)
    box.lat_max = rad2deg(lat_max)
    box.lon_max = rad2deg(lon_max)

    return box


def get_weather_symbol(symbol, hass=None):
    """Get a weather symbol for the symbol value."""
    ret_val = const.FMI_WEATHER_SYMBOL_MAP.get(symbol, "")

    if hass is None or symbol != 1:  # was ret_val != 1 <- always False
        return ret_val

    # Clear as per FMI
    today = date.today()
    sunset = get_astral_event_date(hass, SUN_EVENT_SUNSET, today)
    sunset = sunset.astimezone(tz.tzlocal())

    sunrise = get_astral_event_date(hass, SUN_EVENT_SUNRISE, today)
    sunrise = sunrise.astimezone(tz.tzlocal())

    time_now = datetime.now().astimezone(tz.tzlocal())
    if time_now <= sunrise or time_now >= sunset:
        # Clear night
        ret_val = const.FMI_WEATHER_SYMBOL_MAP[0]

    return ret_val
