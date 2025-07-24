"""Support for retrieving meteorological data from FMI (Finnish Meteorological Institute)."""
import math
from dateutil import tz

from homeassistant.components.weather import (
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_NATIVE_PRECIPITATION,
    ATTR_FORECAST_NATIVE_TEMP,
    ATTR_FORECAST_TIME,
    ATTR_FORECAST_WIND_BEARING,
    ATTR_FORECAST_NATIVE_WIND_SPEED,
    ATTR_FORECAST_NATIVE_TEMP_LOW,
    ATTR_FORECAST_CLOUD_COVERAGE,
    WeatherEntity,
    Forecast,
)
from homeassistant.components.weather.const import (
    ATTR_WEATHER_HUMIDITY,
    ATTR_WEATHER_PRESSURE,
    WeatherEntityFeature,
)
from homeassistant.const import CONF_NAME
import homeassistant.core as ha_core
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

    domain_data = hass.data[const.DOMAIN][config_entry.entry_id]

    coordinator = domain_data[const.COORDINATOR]

    entity_list = [FMIWeatherEntity(name, coordinator)]
    if daily_mode:
        entity_list.append(FMIWeatherEntity(f"{name} (daily)", coordinator,
                                            daily_mode=True))
    if station_id:
        try:
            coordinator = domain_data.get(const.COORDINATOR_OBSERVATION)
            if coordinator is not None:
                entity_list.append(FMIWeatherEntity(
                    f"{name} (observation)", coordinator, station_id=station_id))
        except (KeyError, AttributeError) as error:
            const.LOGGER.error("Unable to setup observation object! ERROR: %s", error)

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
        self.logger = const.LOGGER.getChild("weather")
        super().__init__(coordinator)
        self._daily_mode = daily_mode
        self._observation_mode = station_id
        self._data_func = coordinator.get_observation if station_id else coordinator.get_weather
        _weather = self._data_func()
        _attr_name = [_weather.place if _weather else name]
        _attr_unique_id = [f"{coordinator.unique_id}"]
        _name_extra = ""
        if daily_mode:
            _attr_name.append("(daily)")
            _attr_unique_id.append("daily")
        elif station_id:
            _attr_name.append("(observation)")
            _attr_unique_id.append("observation")
            _name_extra = " Observation"
        self._attr_name = " ".join(_attr_name)
        self._attr_unique_id = "_".join(_attr_unique_id)
        self._attr_device_info = {
            "identifiers": {(const.DOMAIN, coordinator.unique_id)},
            "name": const.NAME + _name_extra,
            "manufacturer": const.MANUFACTURER,
            "entry_type": DeviceEntryType.SERVICE,
        }
        self._attr_should_poll = False
        self._attr_attribution = const.ATTRIBUTION
        # update initial values
        self.update_callback()
        # register the update callback
        coordinator.async_add_listener(self.update_callback)

    @ha_core.callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    def update_callback(self, *_, **__):
        """Update the entity attributes."""
        _fmi: FMIDataUpdateCoordinator = self.coordinator
        _last_update_success = _fmi.last_update_success
        _weather = self._data_func()
        if _weather is None or not _last_update_success:
            self.logger.warning(f"{self._attr_name}: No data available from FMI!")
            return
        _time = _weather.data.time.astimezone(tz.tzlocal())
        self.logger.debug(f"{self._attr_name}: updated: {_last_update_success} time {_time}")
        # Update the entity attributes
        self._attr_native_temperature_unit = self.__get_unit(_weather, "temperature")
        self._attr_native_pressure_unit = self.__get_unit(_weather, "pressure")
        self._attr_native_wind_speed_unit = self.__get_unit(_weather, "wind_speed")
        self._attr_native_temperature = self.__get_value(_weather, "temperature")
        self._attr_humidity = self.__get_value(_weather, "humidity")
        self._attr_native_precipitation = self.__get_value(_weather, "precipitation_amount")
        self._attr_native_wind_speed = self.__get_value(_weather, "wind_speed")
        wind_gust = self.__get_value(_weather, "wind_gust")
        if wind_gust is None or math.isnan(wind_gust):
            wind_gust = self.__get_value(_weather, "wind_max")
        self._attr_native_wind_gust_speed = wind_gust
        self._attr_wind_bearing = self.__get_value(_weather, "wind_direction")
        self._attr_cloud_coverage = self.__get_value(_weather, "cloud_cover")
        self._attr_native_pressure = self.__get_value(_weather, "pressure")
        self._attr_native_dew_point = self.__get_value(_weather, "dew_point")
        self._attr_condition = utils.get_weather_symbol(_weather.data.symbol.value, _fmi.hass)

    def __get_value(self, _weather, name):
        if _weather is None:
            return None
        value = getattr(_weather.data if hasattr(_weather, "data") else _weather, name)
        if value is None or value.value is None or math.isnan(value.value):
            return None
        return value.value

    def __get_unit(self, _weather, name):
        if _weather is None:
            return None
        value = getattr(_weather.data, name)
        if value is None or not value.unit:
            return None
        return value.unit

    def _forecast(self, daily_mode: bool) -> list[Forecast] | None:
        """Return the forecasts."""

        _fmi: FMIDataUpdateCoordinator = self.coordinator
        _forecasts = _fmi.get_forecasts()
        _data = []
        _get_val = self.__get_value

        _item = {}
        _current_day = 0

        for forecast in _forecasts:
            _time = forecast.time.astimezone(tz.tzlocal())
            _temperature = _get_val(forecast, "temperature")
            if not daily_mode or _current_day != _time.day:
                # add a new day
                _current_day = _time.day
                _item = {
                    ATTR_FORECAST_TIME: _time.isoformat(),
                    ATTR_FORECAST_CONDITION: utils.get_weather_symbol(forecast.symbol.value),
                    ATTR_FORECAST_NATIVE_TEMP: _temperature,
                    ATTR_FORECAST_NATIVE_TEMP_LOW: _temperature if daily_mode else None,
                    ATTR_FORECAST_NATIVE_PRECIPITATION: _get_val(forecast, "precipitation_amount"),
                    ATTR_FORECAST_NATIVE_WIND_SPEED: _get_val(forecast, "wind_speed"),
                    ATTR_FORECAST_WIND_BEARING: _get_val(forecast, "wind_direction"),
                    ATTR_WEATHER_PRESSURE: _get_val(forecast, "pressure"),
                    ATTR_WEATHER_HUMIDITY: _get_val(forecast, "humidity"),
                    ATTR_FORECAST_CLOUD_COVERAGE: _get_val(forecast, "cloud_cover"),
                }
                _data.append(_item)

            else:
                # update daily high and low temperature values
                if _item[ATTR_FORECAST_NATIVE_TEMP] < _temperature:
                    _item[ATTR_FORECAST_NATIVE_TEMP] = _temperature
                if _item[ATTR_FORECAST_NATIVE_TEMP_LOW] > _temperature:
                    _item[ATTR_FORECAST_NATIVE_TEMP_LOW] = _temperature
        return _data

    @property
    def forecast(self) -> list[Forecast] | None:
        """Return the forecast array. Legacy version!"""
        return self._forecast(daily_mode=self._daily_mode)

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """Return the hourly forecast in native units."""
        return self._forecast(daily_mode=self._daily_mode)

    async def async_forecast_twice_daily(self) -> list[Forecast] | None:
        """Return the daily forecast in native units."""
        raise NotImplementedError

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """Return the daily forecast in native units."""
        return self._forecast(daily_mode=True)

    async def async_update(self) -> None:
        """Get the latest weather data."""
        _fmi: FMIDataUpdateCoordinator = self.coordinator
        await _fmi.async_refresh()
