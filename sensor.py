"""Support for weather service from FMI (Finnish Meteorological Institute) for sensor platform."""

from datetime import datetime
from dateutil import tz

# Import homeassistant platform dependencies
import homeassistant.const as ha_const
from homeassistant.components.sensor import SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import utils
from . import const


SENSOR_TYPES = {
    "place": ["Place", None, "mdi:city-variant"],
    "weather": ["Condition", None, None],
    "temperature": ["Temperature", ha_const.UnitOfTemperature.CELSIUS, "mdi:thermometer"],
    "wind_speed": ["Wind Speed", ha_const.UnitOfSpeed.METERS_PER_SECOND, "mdi:weather-windy"],
    "wind_direction": ["Wind Direction", "", "mdi:weather-windy"],
    "wind_gust": ["Wind Gust", ha_const.UnitOfSpeed.METERS_PER_SECOND, "mdi:weather-windy"],
    "humidity": ["Humidity", ha_const.PERCENTAGE, "mdi:water"],
    "clouds": ["Cloud Coverage", ha_const.PERCENTAGE, "mdi:weather-cloudy"],
    "rain": ["Rain", ha_const.UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR, "mdi:weather-pouring"],
    "forecast_time": ["Time", None, "mdi:av-timer"],
    "time": ["Best Time Of Day", None, "mdi:av-timer"],
}

SENSOR_LIGHTNING_TYPES = {
    "lightning": ["Lightning Strikes", None, "mdi:weather-lightning"]
}

SENSOR_MAREO_TYPES = {
    "sea_level": ["Sea Level", ha_const.UnitOfLength.CENTIMETERS, "mdi:waves"]
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
    """Common base class for all the sensor types"""

    def __init__(self, name, coordinator, sensor_type, sensor_data):
        """Initialize the sensor base data."""
        super().__init__(coordinator)
        self.client_name = name
        self._name, self._unit_of_measurement, self._icon = sensor_data
        self._fmi = coordinator
        self._state = None
        self.type = sensor_type
        self._unique_id = \
            f"{coordinator.unique_id}_{name.replace(' ', '_')}_{self._name.replace(' ', '_')}"
        try:
            self._fmi_name = coordinator.current.place
        except Exception:
            self._fmi_name = None

        self.update()

    def update(self):
        raise NotImplementedError(
            "Required update method is not implemented")

    # This has not been working correctly so comment it out for now
    # @property
    # def unique_id(self):
    #    return self._unique_id

    @property
    def name(self):
        """Return the name of the sensor."""
        if self._fmi_name is not None:
            return f"{self._fmi_name} {self._name}"
        return f"{self.client_name} {self._name}"

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def state(self):
        """Return the state of the sensor."""
        self.update()
        return self._state


class FMIBestConditionSensor(_BaseSensorClass):
    """Implementation of a FMI Weather sensor with best conditions of the day."""

    @_BaseSensorClass.name.getter
    def name(self):
        """Return the name of the sensor."""
        if self._fmi_name is not None:
            return f"{self._fmi_name} {self._name}"
        return self._name

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self.type == "time":
            _fmi = self._fmi
            if _fmi is not None and _fmi.current is not None:
                return {
                    ha_const.ATTR_LOCATION: _fmi.current.place,
                    ha_const.ATTR_TIME: _fmi.best_time,
                    ha_const.ATTR_TEMPERATURE: _fmi.best_temperature,
                    const.ATTR_HUMIDITY: _fmi.best_humidity,
                    const.ATTR_PRECIPITATION: _fmi.best_precipitation,
                    const.ATTR_WIND_SPEED: _fmi.best_wind_speed,
                    ha_const.ATTR_ATTRIBUTION: const.ATTRIBUTION,
                }

        return {ha_const.ATTR_ATTRIBUTION: const.ATTRIBUTION}

    @staticmethod
    def get_wind_direction_string(wind_direction_in_deg):
        """Get the string interpretation of wind direction in degrees."""

        if wind_direction_in_deg is not None:
            if wind_direction_in_deg <=23:
                return "N"
            elif wind_direction_in_deg > 338:
                return "N"
            elif (23 < wind_direction_in_deg <= 68):
                return "NE"
            elif (68 < wind_direction_in_deg <= 113):
                return "E"
            elif (113 < wind_direction_in_deg <= 158):
                return "SE"
            elif (158 < wind_direction_in_deg <= 203):
                return "S"
            elif (203 < wind_direction_in_deg <= 248):
                return "SW"
            elif (248 < wind_direction_in_deg <= 293):
                return "W"
            elif (293 < wind_direction_in_deg <= 338):
                return "NW"
        return "Unavailable"

    def update(self):
        """Get the latest data from FMI and updates the states."""
        _fmi = self._fmi
        _type = self.type
        if _fmi is None:
            const._LOGGER.debug("FMI: Coordinator is not available")
            return

        if _fmi.current is None:
            const._LOGGER.debug("FMI: Sensor _FMI Current Forecast is unavailable")
            return

        if _type == "place":
            self._state = _fmi.current.place
            return

        source_data = None

        # Update the sensor states
        if _fmi.time_step == 1:
            # Current weather
            source_data = _fmi.current.data
        else:
            # Forecasted weather based on configured time_step - next forecasted hour, if available

            if _fmi.forecast is None:
                const._LOGGER.debug("FMI: Sensor _FMI Hourly Forecast is unavailable")
                return

            # If current time is half past or more then use the hour next to next hour
            # otherwise fallback to the next hour
            if len(_fmi.forecast.forecasts) > 1:
                curr_min = datetime.now().minute
                if curr_min >= 30:
                    source_data = _fmi.forecast.forecasts[1]
            else:
                source_data = _fmi.forecast.forecasts[0]

        if source_data is None:
            const._LOGGER.debug("FMI: Sensor Source data is unavailable")
            return

        _state = None
        if _type == "forecast_time":
            _state = source_data.time.astimezone(tz.tzlocal())
        elif _type == "weather":
            _state = utils.get_weather_symbol(source_data.symbol.value)
        elif _type == "temperature":
            _state = source_data.temperature.value
        elif _type == "wind_speed":
            _state = source_data.wind_speed.value
        elif _type == "wind_direction":
            _state = "Unavailable"
            if source_data.wind_direction is not None:
                _state = self.get_wind_direction_string(source_data.wind_direction.value)
        elif _type == "wind_gust":
            _state = source_data.wind_gust.value
        elif _type == "humidity":
            _state = source_data.humidity.value
        elif _type == "clouds":
            _state = source_data.cloud_cover.value
        elif _type == "rain":
            _state = source_data.precipitation_amount.value
        elif _type == "time":
            _state = _fmi.best_state

        self._state = _state


class FMILightningStrikesSensor(_BaseSensorClass):
    """Implementation of a FMI Lightning strikes sensor."""

    def __init__(self, name, coordinator, sensor_type, sensor_data):
        """Initialize the sensor."""
        self.lightning_data = coordinator.lightning_data
        super().__init__(name, coordinator, sensor_type, sensor_data)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        _data = self.lightning_data
        if _data is None:
            return []

        if len(_data) == 0:
            return []

        return {
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

    def update(self):
        """Get the latest data from FMI and update the states."""

        try:
            self._state = self.lightning_data[0].location
        except Exception:
            const._LOGGER.debug("FMI: Sensor Lightning is unavailable")
            self._state = "Unavailable"


class FMIMareoSensor(_BaseSensorClass):
    """Implementation of a FMI sea water level sensor."""

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""

        mareo_data = self._fmi.mareo_data.sea_levels

        if mareo_data is None:
            return []

        if len(mareo_data) > 1:
            pass
        elif len(mareo_data) > 0:
            return {
                ha_const.ATTR_TIME: mareo_data[0][0],
                "FORECASTS": [],
                ha_const.ATTR_ATTRIBUTION: const.ATTRIBUTION
            }
        else:
            return []

        return {
            ha_const.ATTR_TIME: mareo_data[0][0],
            "FORECASTS": [
                {"time": item[0], "height": item[1]} for item in mareo_data[1:]
            ],
            ha_const.ATTR_ATTRIBUTION: const.ATTRIBUTION,
        }

    def update(self):
        """Get the latest data from FMI and update the states."""

        mareo_data = self._fmi.mareo_data.sea_levels

        try:
            self._state = mareo_data[0][1]
        except Exception:
            const._LOGGER.debug("FMI: Sensor Mareo is unavailable")
            self._state = "Unavailable"
