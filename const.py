"""Constants for the FMI Weather and Sensor integrations."""
import logging
from datetime import date, timedelta

DEFAULT_NAME = "FMI"

LOGGER = logging.getLogger(__package__)

ATTR_HUMIDITY = "relative_humidity"
ATTR_WIND_SPEED = "wind_speed"
ATTR_PRECIPITATION = "precipitation"
ATTR_DISTANCE = "distance"
ATTR_STRIKES = "strikes"
ATTR_PEAK_CURRENT = "peak_current"
ATTR_CLOUD_COVER = "cloud_cover"
ATTR_ELLIPSE_MAJOR = "ellipse_major"

ATTRIBUTION = "Weather Data provided by FMI"

BEST_CONDITION_AVAIL = "available"
BEST_CONDITION_NOT_AVAIL = "not_available"
BEST_COND_SYMBOLS = [1, 2, 21, 3, 31, 32, 41, 42, 51, 52, 91, 92]

CONF_MIN_HUMIDITY = "min_relative_humidity"
CONF_MAX_HUMIDITY = "max_relative_humidity"
CONF_MIN_TEMP = "min_temperature"
CONF_MAX_TEMP = "max_temperature"
CONF_MIN_WIND_SPEED = "min_wind_speed"
CONF_MAX_WIND_SPEED = "max_wind_speed"
CONF_MIN_PRECIPITATION = "min_precipitation"
CONF_MAX_PRECIPITATION = "max_precipitation"

FORECAST_OFFSET = [0, 1, 2, 3, 4, 6, 8, 12, 24]  # Based on API test runs

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=1)
MIN_TIME_BETWEEN_LIGHTNING_UPDATES = timedelta(minutes=1)

# Constants for Lightning strikes
LIGHTNING_LIMIT = 5
BASE_URL = "https://opendata.fmi.fi/wfs?service=WFS&version=2.0.0&request=getFeature&storedquery_id=fmi::observations::lightning::multipointcoverage&timestep=3600&"

# FMI Weather Visibility Constants
FMI_WEATHER_SYMBOL_MAP = {
    1:  "Clear",
    2:  "Partially Clear",
    21: "Light Showers",
    22: "Showers",
    23: "Strong Rain Showers",
    3:  "Cloudy",
    31: "Weak rains",
    32: "Rains",
    33: "Heavy Rains",
    41: "Weak Snow",
    42: "Cloudy",
    43: "Strong Snow",
    51: "Light Snow",
    52: "Snow",
    53: "Heavy Snow",
    61: "Thunderstorms",
    62: "Strong Thunderstorms",
    63: "Thunderstorms",
    64: "Strong Thunderstorms",
    71: "Weak Sleet",
    72: "Sleet",
    73: "Heavy Sleet",
    81: "Light Sleet",
    82: "Sleet",
    83: "Heavy Sleet",
    91: "Fog",
    92: "Fog",
}
