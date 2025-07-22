"""Support for weather service from FMI (Finnish Meteorological Institute) for sensor platform."""

import enum
import math
from datetime import datetime
from dateutil import tz
# Import homeassistant platform dependencies
import homeassistant.const as ha_const
import homeassistant.core as ha_core
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FMIDataUpdateCoordinator
from . import utils
from . import const


class SensorType(enum.IntEnum):
    PLACE = enum.auto()
    WEATHER = enum.auto()
    TEMPERATURE = enum.auto()
    WIND_SPEED = enum.auto()
    WIND_DIR = enum.auto()
    WIND_GUST = enum.auto()
    HUMIDITY = enum.auto()
    CLOUDS = enum.auto()
    RAIN = enum.auto()
    TIME_FORECAST = enum.auto()
    TIME = enum.auto()
    LIGHTNING = enum.auto()
    SEA_LEVEL = enum.auto()


SENSOR_TYPES = {
    SensorType.PLACE: ["Place", None, "mdi:city-variant"],
    SensorType.WEATHER: ["Condition", None, None],
    SensorType.TEMPERATURE: ["Temperature", ha_const.UnitOfTemperature.CELSIUS,
                             "mdi:thermometer"],
    SensorType.WIND_SPEED: ["Wind Speed", ha_const.UnitOfSpeed.METERS_PER_SECOND,
                            "mdi:weather-windy"],
    SensorType.WIND_DIR: ["Wind Direction", "", "mdi:weather-windy"],
    SensorType.WIND_GUST: ["Wind Gust", ha_const.UnitOfSpeed.METERS_PER_SECOND,
                           "mdi:weather-windy"],
    SensorType.HUMIDITY: ["Humidity", ha_const.PERCENTAGE, "mdi:water"],
    SensorType.CLOUDS: ["Cloud Coverage", ha_const.PERCENTAGE, "mdi:weather-cloudy"],
    SensorType.RAIN: ["Rain", ha_const.UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
                      "mdi:weather-pouring"],
    SensorType.TIME_FORECAST: ["Time", None, "mdi:av-timer"],
    SensorType.TIME: ["Best Time Of Day", None, "mdi:av-timer"],
}

SENSOR_LIGHTNING_TYPES = {
    SensorType.LIGHTNING: ["Lightning Strikes", None, "mdi:weather-lightning"]
}

SENSOR_MAREO_TYPES = {
    SensorType.SEA_LEVEL: ["Sea Level", ha_const.UnitOfLength.CENTIMETERS, "mdi:waves"]
}

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the FMI Sensor, including Best Time Of the Day sensor."""
    name = config_entry.data[ha_const.CONF_NAME]
    lightning_mode = config_entry.options.get(const.CONF_LIGHTNING, False)

    coordinator = hass.data[const.DOMAIN][config_entry.entry_id][const.COORDINATOR]

    entity_list = []

    for sensor_type, sensor_data in SENSOR_TYPES.items():
        entity_list.append(
            FMIBestConditionSensor(
                name, coordinator, sensor_type, sensor_data))

    if lightning_mode:
        for sensor_type, sensor_data in SENSOR_LIGHTNING_TYPES.items():
            entity_list.append(
                FMILightningStrikesSensor(name, coordinator, sensor_type, sensor_data))

    for sensor_type, sensor_data in SENSOR_MAREO_TYPES.items():
        entity_list.append(
            FMIMareoSensor(name, coordinator, sensor_type, sensor_data))

    async_add_entities(entity_list, False)


class _BaseSensorClass(CoordinatorEntity):
    """Common base class for all the sensor types."""

    def __init__(self, name, coordinator: FMIDataUpdateCoordinator,
                 sensor_type, sensor_data, only_name=None):
        """Initialize the sensor base data."""
        self.logger = const.LOGGER.getChild("sensor")
        super().__init__(coordinator)
        self.client_name = name
        self._name, self._attr_unit_of_measurement, self._attr_icon = sensor_data
        self.type = sensor_type
        self._attr_unique_id = \
            f"{coordinator.unique_id}_{name.replace(' ', '_')}_{self._name.replace(' ', '_')}"
        if only_name:
            self._attr_name = f"{self._name}"
        else:
            base_name = coordinator.get_current_place()
            if base_name is None:
                base_name = name
            self._attr_name = f"{base_name} {self._name}"
        self._attr_attribution = const.ATTRIBUTION
        self._attr_should_poll = False
        self._attr_state = ha_const.STATE_UNAVAILABLE
        self.update()

        coordinator.async_add_listener(self.update_callback)

    @ha_core.callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    def update_callback(self, *_, **__):
        """Update the entity attributes."""
        _fmi: FMIDataUpdateCoordinator = self.coordinator
        _weather = _fmi.get_weather()
        if not _weather:
            return
        _time = _weather.data.time.astimezone(tz.tzlocal())
        self.logger.debug(f"{self._attr_name}: updated: {_fmi.last_update_success} time {_time}")
        self.update()

    def update(self):
        """Update method prototype."""
        raise NotImplementedError("Required update method is not implemented")


class FMIBestConditionSensor(_BaseSensorClass):
    """Implementation of a FMI Weather sensor with best conditions of the day."""

    def __init__(self, name, coordinator, sensor_type, sensor_data):
        """Initialize the sensor."""
        self.update_state_func = {
            SensorType.WEATHER: self.__update_weather,
            SensorType.TEMPERATURE: self.__update_temperature,
            SensorType.WIND_SPEED: self.__update_wind_speed,
            SensorType.WIND_DIR: self.__update_wind_direction,
            SensorType.WIND_GUST: self.__update_wind_gust,
            SensorType.HUMIDITY: self.__update_humidity,
            SensorType.CLOUDS: self.__update_clouds,
            SensorType.RAIN: self.__update_rain,
            SensorType.TIME_FORECAST: self.__update_forecast_time,
            SensorType.TIME: self.__update_time,
        }.get(sensor_type, self.__update_dummy)
        super().__init__(name, coordinator, sensor_type, sensor_data, only_name=True)

    @staticmethod
    def get_wind_direction_string(wind_direction_in_deg):
        """Get the string interpretation of wind direction in degrees."""

        if wind_direction_in_deg is None or \
                wind_direction_in_deg < 0 or wind_direction_in_deg > 360:
            return ha_const.STATE_UNAVAILABLE

        if wind_direction_in_deg <= 23 or wind_direction_in_deg > 338:
            return "N"
        if 23 < wind_direction_in_deg <= 68:
            return "NE"
        if 68 < wind_direction_in_deg <= 113:
            return "E"
        if 113 < wind_direction_in_deg <= 158:
            return "SE"
        if 158 < wind_direction_in_deg <= 203:
            return "S"
        if 203 < wind_direction_in_deg <= 248:
            return "SW"
        if 248 < wind_direction_in_deg <= 293:
            return "W"
        if 293 < wind_direction_in_deg <= 338:
            return "NW"
        return ha_const.STATE_UNAVAILABLE

    def __convert_float(self, source_data, name):
        value = getattr(source_data, name)
        if value is None or math.isnan(value.value):
            self._attr_state = ha_const.STATE_UNAVAILABLE
            return
        self._attr_state = value.value

    def __update_dummy(self, source_data):
        _ = source_data
        self._attr_state = ha_const.STATE_UNKNOWN

    def __update_forecast_time(self, source_data):
        self._attr_state = source_data.time.astimezone(tz.tzlocal()).strftime("%H:%M")

    def __update_weather(self, source_data):
        self._attr_state = utils.get_weather_symbol(source_data.symbol.value)

    def __update_temperature(self, source_data):
        self.__convert_float(source_data, "temperature")

    def __update_wind_speed(self, source_data):
        self.__convert_float(source_data, "wind_speed")

    def __update_wind_direction(self, source_data):
        if source_data.wind_direction is None:
            self._attr_state = ha_const.STATE_UNAVAILABLE
            return
        self._attr_state = self.get_wind_direction_string(source_data.wind_direction.value)

    def __update_wind_gust(self, source_data):
        self.__convert_float(source_data, "wind_gust")

    def __update_humidity(self, source_data):
        self.__convert_float(source_data, "humidity")

    def __update_clouds(self, source_data):
        self.__convert_float(source_data, "cloud_cover")

    def __update_rain(self, source_data):
        self.__convert_float(source_data, "precipitation_amount")

    def __update_time(self, source_data):
        _ = source_data
        _fmi: FMIDataUpdateCoordinator = self.coordinator
        if _fmi.best_time is None:
            self._attr_state = ha_const.STATE_UNAVAILABLE
            return
        self._attr_state = _fmi.best_time.strftime("%H:%M")

    def update(self):
        """Update the state of the weather sensor."""

        self.logger.debug("FMI: Sensor %s is updating", self._attr_name)

        _fmi: FMIDataUpdateCoordinator = self.coordinator
        weather = _fmi.get_weather()

        if weather is None:
            return

        # update the extra state attributes
        self._attr_extra_state_attributes = {
            ha_const.ATTR_LOCATION: weather.place,
            ha_const.ATTR_TIME: _fmi.best_time,
            ha_const.ATTR_TEMPERATURE: _fmi.best_temperature,
            const.ATTR_HUMIDITY: _fmi.best_humidity,
            const.ATTR_PRECIPITATION: _fmi.best_precipitation,
            const.ATTR_WIND_SPEED: _fmi.best_wind_speed,
            ha_const.ATTR_ATTRIBUTION: const.ATTRIBUTION,
        }

        if self.type == SensorType.PLACE:
            self._attr_state = weather.place
            return

        source_data = None

        # Update the sensor states
        if _fmi.time_step == 1:
            # Current weather
            source_data = weather.data
        else:
            # Forecasted weather based on configured time_step - next forecasted hour, if available

            _forecasts = _fmi.get_forecasts()

            if not _forecasts:
                self.logger.debug("FMI: Sensor _FMI Hourly Forecast is unavailable")
                return

            # If current time is half past or more then use the hour next to next hour
            # otherwise fallback to the next hour
            if len(_forecasts) > 1:
                curr_min = datetime.now().minute
                source_data = _forecasts[1 if curr_min >= 30 else 0]
            else:
                source_data = _forecasts[0]

        if source_data is None:
            self._attr_state = ha_const.STATE_UNAVAILABLE
            self.logger.debug("FMI: Sensor Source data is unavailable")
            return

        self.update_state_func(source_data)


class FMILightningStrikesSensor(_BaseSensorClass):
    """Implementation of a FMI Lightning strikes sensor."""

    def update(self):
        """Update the state of the lightning sensor."""

        self.logger.debug("FMI: update lightning sensor %s", self._attr_name)

        _fmi: FMIDataUpdateCoordinator = self.coordinator
        _data = _fmi.lightning_data

        if not _data:
            self.logger.debug("FMI: Sensor lightning is unavailable")
            return

        self._attr_state = _data[0].location

        # update the extra state attributes
        self._attr_extra_state_attributes = {
            ha_const.ATTR_LOCATION: _data[0].location,
            ha_const.ATTR_TIME: _data[0].time,
            const.ATTR_DISTANCE: _data[0].distance,
            const.ATTR_STRIKES: _data[0].strikes,
            const.ATTR_PEAK_CURRENT: _data[0].peak_current,
            const.ATTR_CLOUD_COVER: _data[0].cloud_cover,
            const.ATTR_ELLIPSE_MAJOR: _data[0].ellipse_major,
            "OBSERVATIONS": [
                {
                    ha_const.ATTR_LOCATION: strike.location,
                    ha_const.ATTR_TIME: strike.time,
                    const.ATTR_DISTANCE: strike.distance,
                    const.ATTR_STRIKES: strike.strikes,
                    const.ATTR_PEAK_CURRENT: strike.peak_current,
                    const.ATTR_CLOUD_COVER: strike.cloud_cover,
                    const.ATTR_ELLIPSE_MAJOR: strike.ellipse_major,
                }
                for strike in _data[1:]
            ],
            ha_const.ATTR_ATTRIBUTION: const.ATTRIBUTION,
        }


class FMIMareoSensor(_BaseSensorClass):
    """Implementation of a FMI sea water level sensor."""

    def update(self):
        """Update the state of the mareo sensor."""

        self.logger.debug("FMI: update mareo sensor %s", self._attr_name)

        _fmi: FMIDataUpdateCoordinator = self.coordinator
        mareo = _fmi.mareo_data

        if not mareo or not mareo.size():
            self.logger.debug("FMI: Sensor mareo is unavailable")
            return

        mareo_data = mareo.get_values()

        self._attr_state = mareo_data[0].sea_level

        # update the extra state attributes
        self._attr_extra_state_attributes = {
            ha_const.ATTR_TIME: mareo_data[0].time,
            "FORECASTS": [
                {"time": item.time, "height": item.sea_level} for item in mareo_data[1:]
            ],
            ha_const.ATTR_ATTRIBUTION: const.ATTRIBUTION,
        }
