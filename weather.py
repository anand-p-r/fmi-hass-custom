"""Support for retrieving meteorological data from FMI (Finnish Meteorological Institute)."""
from dateutil import tz

from homeassistant.components.weather import (
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_NATIVE_PRECIPITATION,
    ATTR_FORECAST_NATIVE_TEMP,
    ATTR_FORECAST_TIME,
    ATTR_FORECAST_WIND_BEARING,
    ATTR_FORECAST_NATIVE_WIND_SPEED,
    ATTR_FORECAST_NATIVE_TEMP_LOW,
    WeatherEntity,
    Forecast,
)
from homeassistant.components.weather.const import (
    ATTR_WEATHER_HUMIDITY,
    ATTR_WEATHER_PRESSURE,
    WeatherEntityFeature,
)
from homeassistant.const import CONF_NAME
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FMIDataUpdateCoordinator
from . import const
from . import utils


PARALLEL_UPDATES = 1


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add an FMI weather entity from a config_entry."""
    name = config_entry.data[CONF_NAME]
    daily_mode = config_entry.options.get(const.CONF_DAILY_MODE, False)
    station_id = bool(config_entry.options.get(const.CONF_OBSERVATION_STATION, 0))

    coordinator = hass.data[const.DOMAIN][config_entry.entry_id][const.COORDINATOR]

    entity_list = [FMIWeatherEntity(name, coordinator)]
    if daily_mode:
        entity_list.append(FMIWeatherEntity(f"{name} (daily)", coordinator,
                                            daily_mode=True))
    if station_id:
        try:
            entity_list.append(FMIWeatherEntity(f"{name} (observation)", coordinator,
                                                station_id=station_id))
        except AttributeError:
            const.LOGGER.error("Unable to setup observation object!")

    async_add_entities(entity_list, False)


class FMIWeatherEntity(CoordinatorEntity, WeatherEntity):
    """Define an FMI Weather Entity."""

    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_HOURLY |
        WeatherEntityFeature.FORECAST_DAILY
    )

    def __init__(self, name, coordinator: FMIDataUpdateCoordinator,
                 station_id: bool = False, daily_mode: bool = False):
        """Initialize FMI weather object."""
        super().__init__(coordinator)
        self._daily_mode = daily_mode
        self._observation_mode = station_id
        self._data_func = coordinator.get_observation if station_id else coordinator.get_weather
        _weather = self._data_func()
        _attr_name = [_weather.place if _weather else name]
        _attr_unique_id = [f"{coordinator.unique_id}"]
        if daily_mode:
            _attr_name.append("(daily)")
            _attr_unique_id.append("daily")
        elif station_id:
            _attr_name.append("(observation)")
            _attr_unique_id.append("observation")
        self._attr_name = " ".join(_attr_name)
        self._attr_unique_id = "_".join(_attr_unique_id)
        self._attr_device_info = {
            "identifiers": {(const.DOMAIN, coordinator.unique_id)},
            "name": const.NAME,
            "manufacturer": const.MANUFACTURER,
            "entry_type": DeviceEntryType.SERVICE,
        }
        self._attr_attribution = const.ATTRIBUTION
        self._attr_native_temperature_unit = _weather.data.temperature.unit
        self._attr_native_pressure_unit = _weather.data.pressure.unit
        self._attr_native_wind_speed_unit = _weather.data.wind_speed.unit

    @property
    def available(self):
        """Return if weather data is available from FMI."""
        return self._data_func() is not None

    @property
    def native_temperature(self):
        """Return the temperature."""
        _weather = self._data_func()
        if _weather is None:
            return None
        return _weather.data.temperature.value

    @property
    def humidity(self):
        """Return the humidity."""
        _weather = self._data_func()
        if _weather is None:
            return None
        return _weather.data.humidity.value

    @property
    def native_precipitation(self):
        """Return the precipitation."""
        _weather = self._data_func()
        if _weather is None:
            return None
        return _weather.data.precipitation_amount.value

    @property
    def native_wind_speed(self):
        """Return the wind speed."""
        _weather = self._data_func()
        if _weather is None:
            return None
        return _weather.data.wind_speed.value

    @property
    def wind_bearing(self):
        """Return the wind bearing."""
        _weather = self._data_func()
        if _weather is None:
            return None
        return _weather.data.wind_direction.value

    @property
    def native_pressure(self):
        """Return the pressure."""
        _weather = self._data_func()
        if _weather is None:
            return None
        return _weather.data.pressure.value

    @property
    def native_dew_point(self) -> float | None:
        """Return the dew point."""
        _weather = self._data_func()
        if _weather is None:
            return None
        return _weather.data.dew_point.value

    @property
    def condition(self):
        """Return the condition."""
        _weather = self._data_func()
        if _weather is None:
            return None
        _fmi: FMIDataUpdateCoordinator = self.coordinator
        return utils.get_weather_symbol(_weather.data.symbol.value, _fmi.hass)

    def _forecast(self, daily_mode: bool = False) -> list[Forecast] | None:
        """Return the forecast array."""

        _fmi: FMIDataUpdateCoordinator = self.coordinator
        _forecasts = _fmi.get_forecasts()
        data = []

        if daily_mode or self._daily_mode:
            # Daily mode, aggregate forecast for every day
            day = 0
            for forecast in _forecasts:
                fc_time = forecast.time.astimezone(tz.tzlocal())
                if day != fc_time.day:
                    day = fc_time.day
                    data.append(
                        {
                            ATTR_FORECAST_TIME: fc_time.isoformat(),
                            ATTR_FORECAST_CONDITION: utils.get_weather_symbol(
                                forecast.symbol.value),
                            ATTR_FORECAST_NATIVE_TEMP: forecast.temperature.value,
                            ATTR_FORECAST_NATIVE_TEMP_LOW: forecast.temperature.value,
                            ATTR_FORECAST_NATIVE_PRECIPITATION: forecast.precipitation_amount.value,
                            ATTR_FORECAST_NATIVE_WIND_SPEED: forecast.wind_speed.value,
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
            return data

        for forecast in _forecasts:
            fc_time = forecast.time.astimezone(tz.tzlocal())
            data.append(
                {
                    ATTR_FORECAST_TIME: fc_time.isoformat(),
                    ATTR_FORECAST_CONDITION: utils.get_weather_symbol(forecast.symbol.value),
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
        _fmi: FMIDataUpdateCoordinator = self.coordinator
        await _fmi.async_refresh()
