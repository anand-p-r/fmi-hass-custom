"""Common utilities for the FMI Weather and Sensor integrations."""

import math
from datetime import date, datetime
from dateutil import tz
from .const import (
    BOUNDING_BOX_LAT_MAX,
    BOUNDING_BOX_LAT_MIN,
    BOUNDING_BOX_LONG_MAX,
    BOUNDING_BOX_LONG_MIN,
    FMI_WEATHER_SYMBOL_MAP,
)
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.const import SUN_EVENT_SUNSET, SUN_EVENT_SUNRISE


class BoundingBox(object):
    def __init__(self, *args, **kwargs):
        self.lat_min = None
        self.lon_min = None
        self.lat_max = None
        self.lon_max = None


def get_bounding_box_covering_finland():
    box = BoundingBox()
    box.lat_min = BOUNDING_BOX_LAT_MIN
    box.lon_min = BOUNDING_BOX_LONG_MIN
    box.lat_max = BOUNDING_BOX_LAT_MAX
    box.lon_max = BOUNDING_BOX_LONG_MAX

    return box


def get_bounding_box(latitude_in_degrees, longitude_in_degrees, half_side_in_km):
    assert half_side_in_km > 0
    assert latitude_in_degrees >= -90.0 and latitude_in_degrees <= 90.0
    assert longitude_in_degrees >= -180.0 and longitude_in_degrees <= 180.0

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
    ret_val = ""
    if symbol in FMI_WEATHER_SYMBOL_MAP.keys():
        ret_val = FMI_WEATHER_SYMBOL_MAP[symbol]
        if hass is not None and ret_val == 1:  # Clear as per FMI
            today = date.today()
            sunset = get_astral_event_date(hass, SUN_EVENT_SUNSET, today)
            sunset = sunset.astimezone(tz.tzlocal())

            sunrise = get_astral_event_date(hass, SUN_EVENT_SUNRISE, today)
            sunrise = sunrise.astimezone(tz.tzlocal())

            if (datetime.now().astimezone(tz.tzlocal()) <= sunrise) or (
                datetime.now().astimezone(tz.tzlocal()) >= sunset
            ):
                # Clear night
                ret_val = FMI_WEATHER_SYMBOL_MAP[0]
    return ret_val
