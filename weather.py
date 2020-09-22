"""Support for retrieving meteorological data from FMI (Finnish Meteorological Institute)."""

from datetime import timedelta
from dateutil import tz

import fmi_weather_client as fmi
from fmi_weather_client.errors import ClientError, ServerError
import voluptuous as vol

# Import homeassistant platform dependencies
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_OFFSET,
)

import homeassistant.components.sun as sun
from homeassistant.components.weather import (
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_PRECIPITATION,
    ATTR_FORECAST_TEMP,
    ATTR_FORECAST_TIME,
    ATTR_FORECAST_WIND_BEARING,
    ATTR_FORECAST_WIND_SPEED,
    ATTR_WEATHER_HUMIDITY,
    ATTR_WEATHER_PRESSURE,
    PLATFORM_SCHEMA,
    WeatherEntity,
)

import homeassistant.helpers.config_validation as cv
from homeassistant.util import Throttle

from .const import (
    FORECAST_OFFSET,
    DEFAULT_NAME,
    ATTRIBUTION,
    FMI_WEATHER_SYMBOL_MAP,
    MIN_TIME_BETWEEN_UPDATES
)


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_LATITUDE): cv.latitude,
        vol.Optional(CONF_LONGITUDE): cv.longitude,
        vol.Optional(CONF_OFFSET, default=1): vol.In(FORECAST_OFFSET),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the FMI weather."""
    latitude = config.get(CONF_LATITUDE, hass.config.latitude)
    longitude = config.get(CONF_LONGITUDE, hass.config.longitude)
    name = config.get(CONF_NAME)
    time_step = config.get(CONF_OFFSET)

    fmi_weather = FMI(hass, latitude, longitude, time_step)

    add_entities([FMIWeather(name, fmi_weather)], True)


class FMI:
    """Get the latest data from FMI."""

    def __init__(self, hass, latitude, longitude, time_step):
        """Initialize the data object."""
        self.latitude = latitude
        self.longitude = longitude
        self.time_step = time_step

        self.current = None
        self.hourly = None
        self.hass = hass

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Get the latest data - current weather and forecasted weather from FMI."""
        # Current Weather
        try:
            self.current = fmi.weather_by_coordinates(self.latitude, self.longitude)

        except ClientError as err:
            err_string = (
                "Client error with status "
                + str(err.status_code)
                + " and message "
                + err.message
            )
            LOGGER.error(err_string)
        except ServerError as err:
            err_string = (
                "Server error with status "
                + str(err.status_code)
                + " and message "
                + err.body
            )
            LOGGER.error(err_string)
            self.current = None

        # Hourly weather for 24hrs.
        try:
            self.hourly = fmi.forecast_by_coordinates(
                self.latitude, self.longitude, timestep_hours=self.time_step
            )

        except ClientError as err:
            err_string = (
                "Client error with status "
                + str(err.status_code)
                + " and message "
                + err.message
            )
            LOGGER.error(err_string)
        except ServerError as err:
            err_string = (
                "Server error with status "
                + str(err.status_code)
                + " and message "
                + err.body
            )
            LOGGER.error(err_string)
            self.hourly = None


class FMIWeather(WeatherEntity):
    """Representation of a weather condition."""

    def __init__(self, name, fmi_weather):
        """Initialize FMI weather object."""
        self._name = name
        self._fmi = fmi_weather

    @property
    def available(self):
        """Return if weather data is available from FMI."""
        return self._fmi.current is not None

    @property
    def attribution(self):
        """Return the attribution."""
        return ATTRIBUTION

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def temperature(self):
        """Return the temperature."""
        return self._fmi.current.data.temperature.value

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._fmi.current.data.temperature.unit

    @property
    def humidity(self):
        """Return the humidity."""
        return self._fmi.current.data.humidity.value

    @property
    def precipitation(self):
        """Return the humidity."""
        return self._fmi.current.data.precipitation_amount.value

    @property
    def wind_speed(self):
        """Return the wind speed."""
        return round(
            self._fmi.current.data.wind_speed.value * 3.6, 1
        )  # Convert m/s to km/hr

    @property
    def wind_bearing(self):
        """Return the wind bearing."""
        return self._fmi.current.data.wind_direction.value

    @property
    def pressure(self):
        """Return the pressure."""
        return self._fmi.current.data.pressure.value

    @property
    def condition(self):
        """Return the condition."""
        if self._fmi.current.data.symbol.value in FMI_WEATHER_SYMBOL_MAP.keys():
            if self._fmi.current.data.symbol.value == 1:  # Clear as per FMI
                if self._fmi.hass.states.get("sun.sun") == sun.STATE_BELOW_HORIZON:
                    # Clear night
                    return FMI_WEATHER_SYMBOL_MAP[0]
            return FMI_WEATHER_SYMBOL_MAP[self._fmi.current.data.symbol.value]

        return ""

    @property
    def forecast(self):
        """Return the forecast array."""
        if self._fmi.hourly is None:
            return None

        def get_weather_symbol(symbol):
            if symbol in FMI_WEATHER_SYMBOL_MAP.keys():
                return FMI_WEATHER_SYMBOL_MAP[symbol]

            return ""

        data = None

        data = [
            {
                ATTR_FORECAST_TIME: forecast.time.astimezone(tz.tzlocal()),
                ATTR_FORECAST_CONDITION: get_weather_symbol(forecast.symbol.value),
                ATTR_FORECAST_TEMP: forecast.temperature.value,
                ATTR_FORECAST_PRECIPITATION: forecast.precipitation_amount.value,
                ATTR_FORECAST_WIND_SPEED: forecast.wind_speed.value,
                ATTR_FORECAST_WIND_BEARING: forecast.wind_direction.value,
                ATTR_WEATHER_PRESSURE: forecast.pressure.value,
                ATTR_WEATHER_HUMIDITY: forecast.humidity.value,
            }
            for forecast in self._fmi.hourly.forecasts
        ]

        # if the first few precipitation values in forecast is 0, no need to include them
        # in UI
        include_precipitation = False
        len_check = 5 if len(data) > 5 else len(data)
        for _, dt_w in zip(range(len_check), data):
            if dt_w[ATTR_FORECAST_PRECIPITATION] > 0.0:
                include_precipitation = True
                break

        if include_precipitation is False:
            for _, dt_w in zip(range(len_check), data):
                del dt_w[ATTR_FORECAST_PRECIPITATION]

        return data

    def update(self):
        """Get the latest data from FMI."""
        self._fmi.update()
