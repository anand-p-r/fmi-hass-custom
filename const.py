"""Constants for the FMI Weather and Sensor integrations."""
from datetime import timedelta
import logging

_LOGGER = logging.getLogger(__package__)

DOMAIN = "fmi"
NAME = "FMI"
MANUFACTURER = "Finnish Meteorological Institute"

COORDINATOR = "coordinator"
MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=30)
UNDO_UPDATE_LISTENER = "undo_update_listener"

CONF_MIN_HUMIDITY = "min_relative_humidity"
CONF_MAX_HUMIDITY = "max_relative_humidity"
CONF_MIN_TEMP = "min_temperature"
CONF_MAX_TEMP = "max_temperature"
CONF_MIN_WIND_SPEED = "min_wind_speed"
CONF_MAX_WIND_SPEED = "max_wind_speed"
CONF_MIN_PRECIPITATION = "min_precipitation"
CONF_MAX_PRECIPITATION = "max_precipitation"

HUMIDITY_RANGE = list(range(1, 101))
TEMP_RANGE = list(range(-40, 50))
WIND_SPEED = list(range(0, 31))

FORECAST_OFFSET = [1, 2, 3, 4, 6, 8, 12, 24]  # Based on API test runs
DEFAULT_NAME = "FMI"

ATTR_DISTANCE = "distance"
ATTR_STRIKES = "strikes"
ATTR_PEAK_CURRENT = "peak_current"
ATTR_CLOUD_COVER = "cloud_cover"
ATTR_ELLIPSE_MAJOR = "ellipse_major"
ATTR_FORECAST = CONF_FORECAST = "forecast"
ATTR_HUMIDITY = "relative_humidity"
ATTR_WIND_SPEED = "wind_speed"
ATTR_PRECIPITATION = "precipitation"
ATTR_SEAHEIGHT_NOW = "sea_level_now"
ATTR_SEAHEIGHT_FORC = "sea_level_6hrs"

ATTRIBUTION = "Weather Data provided by FMI"

BEST_COND_SYMBOLS = [1, 2, 21, 3, 31, 32, 41, 42, 51, 52, 91, 92]
BEST_CONDITION_AVAIL = "available"
BEST_CONDITION_NOT_AVAIL = "not_available"

# Constants for Lightning strikes
LIGHTNING_LIMIT = 5
BASE_URL = "https://opendata.fmi.fi/wfs?service=WFS&version=2.0.0&request=getFeature&storedquery_id=fmi::observations::lightning::multipointcoverage&timestep=3600&"

# Constants for Mareograph data
#BASE_MAREO_OBS_URL = "https://opendata.fmi.fi/wfs?service=WFS&version=2.0.0&request=getFeature&storedquery_id=fmi::observations::mareograph::simple&fmisid=132310&timestep=30"
BASE_MAREO_FORC_URL = "http://opendata.fmi.fi/wfs?service=WFS&version=2.0.0&request=getFeature&storedquery_id=fmi::forecast::oaas::sealevel::point::simple&timestep=30&"
# example: http://opendata.fmi.fi/wfs?service=WFS&version=2.0.0&request=getFeature&storedquery_id=fmi::forecast::oaas::sealevel::point::simple&timestep=30&latlon=60.0,24.4&starttime=2021-04-11T13:24:00Z
#future maybe for sea temperature: http://opendata.fmi.fi/wfs?service=WFS&version=2.0.0&request=getFeature&storedquery_id=fmi::forecast::oaas::sealevel::point::simple&timestep=30&latlon=60.0,24.0&starttime=2021-04-11T13:24:00Z

# FMI Weather Visibility Constants
FMI_WEATHER_SYMBOL_MAP = {
    0: "clear-night",  # custom value 0 - not defined by FMI
    1: "sunny",  # "Clear",
    2: "partlycloudy",  # "Partially Clear",
    21: "rainy",  # "Light Showers",
    22: "pouring",  # "Showers",
    23: "pouring",  # "Strong Rain Showers",
    3: "cloudy",  # "Cloudy",
    31: "rainy",  # "Weak rains",
    32: "rainy",  # "Rains",
    33: "pouring",  # "Heavy Rains",
    41: "snowy-rainy",  # "Weak Snow",
    42: "cloudy",  # "Cloudy",
    43: "snowy",  # "Strong Snow",
    51: "snowy",  # "Light Snow",
    52: "snowy",  # "Snow",
    53: "snowy",  # "Heavy Snow",
    61: "lightning",  # "Thunderstorms",
    62: "lightning-rainy",  # "Strong Thunderstorms",
    63: "lightning",  # "Thunderstorms",
    64: "lightning-rainy",  # "Strong Thunderstorms",
    71: "rainy",  # "Weak Sleet",
    72: "rainy",  # "Sleet",
    73: "pouring",  # "Heavy Sleet",
    81: "rainy",  # "Light Sleet",
    82: "rainy",  # "Sleet",
    83: "pouring",  # "Heavy Sleet",
    91: "fog",  # "Fog",
    92: "fog",  # "Fog"
}
