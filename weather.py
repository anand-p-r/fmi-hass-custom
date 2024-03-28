"""Support for retrieving meteorological data from FMI (Finnish Meteorological Institute)."""
from dateutil import tz

from homeassistant.components.weather import (
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_NATIVE_PRECIPITATION,
    ATTR_FORECAST_NATIVE_TEMP,
    ATTR_FORECAST_TIME,
    ATTR_FORECAST_WIND_BEARING,
    ATTR_FORECAST_NATIVE_WIND_SPEED,
    ATTR_WEATHER_HUMIDITY,
    ATTR_WEATHER_PRESSURE,
    ATTR_FORECAST_NATIVE_TEMP_LOW,
    WeatherEntity,
    WeatherEntityFeature,
    Forecast,
)

from awesomeversion import AwesomeVersion
from homeassistant.const import CONF_NAME, __version__ as HA_VERSION
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import CONF_DAILY_MODE

from .utils import get_weather_symbol

from .const import _LOGGER, ATTRIBUTION, COORDINATOR, DOMAIN, MANUFACTURER, NAME

PARALLEL_UPDATES = 1

CURRENT_HA_VERSION = AwesomeVersion(HA_VERSION)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add an FMI weather entity from a config_entry."""
    name = config_entry.data[CONF_NAME]
    daily_mode = config_entry.options.get(CONF_DAILY_MODE, False)

    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]

    entity_list = [FMIWeatherEntity(name, coordinator, False)]
    if daily_mode:
        entity_list.append(FMIWeatherEntity(f"{name} (daily)", coordinator, True))

    async_add_entities(entity_list, False)


class FMIWeatherEntity(CoordinatorEntity, WeatherEntity):
    """Define an FMI Weather Entity."""

    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_HOURLY |
        WeatherEntityFeature.FORECAST_DAILY
    )

    def __init__(self, name, coordinator, daily_mode):
        """Initialize FMI weather object."""
        super().__init__(coordinator)
        self._name = name
        self._attrs = {}
        self._unit_system = "Metric"
        self._fmi = coordinator
        self._daily_mode = daily_mode
        self._id = (
            self.coordinator.unique_id
            if not daily_mode
            else f"{self.coordinator.unique_id}_daily"
        )

    @property
    def name(self):
        """Return the name of the place based on Lat/Long."""
        if self._fmi is None or self._fmi.current is None:
            return self._name

        if self._daily_mode:
            return f"{self._fmi.current.place} (daily)"
        return self._fmi.current.place

    @property
    def attribution(self):
        """Return the attribution."""
        return ATTRIBUTION

    @property
    def unique_id(self):
        """Return a unique_id for this entity."""
        return self._id

    @property
    def device_info(self):
        """Return the device info."""
        info = {
            "identifiers": {(DOMAIN, self.coordinator.unique_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
        }

        # Legacy fallback can be removed when minimum required
        # HA version is 2021.12.
        if CURRENT_HA_VERSION >= "2021.12.0b0":
            from homeassistant.helpers.device_registry import DeviceEntryType

            info["entry_type"] = DeviceEntryType.SERVICE
        else:
            info["entry_type"] = "service"

        return info

    @property
    def available(self):
        """Return if weather data is available from FMI."""
        if self._fmi is None:
            return False

        return self._fmi.current is not None

    @property
    def native_temperature(self):
        """Return the temperature."""
        if self._fmi is None:
            return None

        return self._fmi.current.data.temperature.value

    @property
    def native_temperature_unit(self):
        """Return the unit of measurement."""
        if self._fmi is None:
            return None

        return self._fmi.current.data.temperature.unit

    @property
    def humidity(self):
        """Return the humidity."""
        if self._fmi is None:
            return None

        return self._fmi.current.data.humidity.value

    @property
    def native_precipitation(self):
        """Return the humidity."""
        if self._fmi is None:
            return None

        return self._fmi.current.data.precipitation_amount.value

    @property
    def native_wind_speed(self):
        """Return the wind speed."""
        if self._fmi is None:
            return None

        return round(
            self._fmi.current.data.wind_speed.value * 3.6, 1
        )  # Convert m/s to km/hr

    @property
    def wind_bearing(self):
        """Return the wind bearing."""
        if self._fmi is None:
            return None

        return self._fmi.current.data.wind_direction.value

    @property
    def native_pressure(self):
        """Return the pressure."""
        if self._fmi is None:
            return None

        return self._fmi.current.data.pressure.value

    @property
    def native_dew_point(self) -> float | None:
        """Return the dew point."""
        if self._fmi is None:
            return None

        return self._fmi.current.data.dew_point.value

    @property
    def condition(self):
        """Return the condition."""
        if self._fmi is None:
            return None

        return get_weather_symbol(self._fmi.current.data.symbol.value, self._fmi.hass)

    def _forecast(self, daily_mode: bool = False) -> list[Forecast] | None:
        """Return the forecast array."""
        if self._fmi is None:
            _LOGGER.debug("FMI: Coordinator is not available!")
            return None

        if self._fmi.forecast is None:
            return None

        if daily_mode or self._daily_mode:
            # Daily mode, aggregate forecast for every day
            day = 0
            data = []
            for forecast in self._fmi.forecast.forecasts:
                fc_time = forecast.time.astimezone(tz.tzlocal())
                if day != fc_time.day:
                    day = fc_time.day
                    data.append(
                        {
                            ATTR_FORECAST_TIME: fc_time.isoformat(),
                            ATTR_FORECAST_CONDITION: get_weather_symbol(
                                forecast.symbol.value
                            ),
                            ATTR_FORECAST_NATIVE_TEMP: forecast.temperature.value,
                            ATTR_FORECAST_NATIVE_TEMP_LOW: forecast.temperature.value,
                            ATTR_FORECAST_NATIVE_PRECIPITATION: forecast.precipitation_amount.value,
                            ATTR_FORECAST_NATIVE_WIND_SPEED: round(
                            forecast.wind_speed.value * 3.6, 1
                            ),  # Convert m/s to km/hr
                            ATTR_FORECAST_WIND_BEARING: forecast.wind_direction.value,
                            ATTR_WEATHER_PRESSURE: forecast.pressure.value,
                            ATTR_WEATHER_HUMIDITY: forecast.humidity.value,
                        }
                    )
                else:
                    if data[-1][ATTR_FORECAST_NATIVE_TEMP] < forecast.temperature.value:
                        data[-1][ATTR_FORECAST_NATIVE_TEMP] = forecast.temperature.value
                    if data[-1][ATTR_FORECAST_NATIVE_TEMP_LOW] > forecast.temperature.value:
                        data[-1][ATTR_FORECAST_NATIVE_TEMP_LOW] = forecast.temperature.value
        else:
            data = []
            for forecast in self._fmi.forecast.forecasts:
                fc_time = forecast.time.astimezone(tz.tzlocal())
                data.append(
                    {
                        ATTR_FORECAST_TIME: fc_time.isoformat(),
                        ATTR_FORECAST_CONDITION: get_weather_symbol(
                            forecast.symbol.value
                        ),
                        ATTR_FORECAST_NATIVE_TEMP: forecast.temperature.value,
                        ATTR_FORECAST_NATIVE_PRECIPITATION: forecast.precipitation_amount.value,
                        ATTR_FORECAST_NATIVE_WIND_SPEED: forecast.wind_speed.value,
                        ATTR_FORECAST_WIND_BEARING: forecast.wind_direction.value,
                        ATTR_WEATHER_PRESSURE: forecast.pressure.value,
                        ATTR_WEATHER_HUMIDITY: forecast.humidity.value,
                    }
                )

        return data

    @property
    def forecast(self) -> list[Forecast] | None:
        """Return the forecast array. Legacy version!"""
        return self._forecast()

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """Return the hourly forecast in native units."""
        return self._forecast()

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """Return the daily forecast in native units."""
        return self._forecast(daily_mode=True)

    async def async_update(self) -> None:
        """Get the latest weather data."""
        await self._fmi.async_refresh()
