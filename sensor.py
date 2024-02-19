"""Support for weather service from FMI (Finnish Meteorological Institute) for sensor platform."""

from datetime import datetime
from dateutil import tz

# Import homeassistant platform dependencies
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_LOCATION,
    ATTR_TEMPERATURE,
    ATTR_TIME,
    CONF_NAME,
    PERCENTAGE,
    UnitOfSpeed,
    UnitOfTemperature,
)

from homeassistant.components.sensor import (
    SensorStateClass
)

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_LIGHTNING,
    _LOGGER,
    ATTRIBUTION,
    DOMAIN,
    ATTR_HUMIDITY,
    ATTR_WIND_SPEED,
    ATTR_PRECIPITATION,
    ATTR_DISTANCE,
    ATTR_STRIKES,
    ATTR_PEAK_CURRENT,
    ATTR_CLOUD_COVER,
    ATTR_ELLIPSE_MAJOR,
    COORDINATOR
)

from .utils import (
    get_weather_symbol
)

SENSOR_TYPES = {
    "place": ["Place", None],
    "weather": ["Condition", None],
    "temperature": ["Temperature", UnitOfTemperature.CELSIUS],
    "wind_speed": ["Wind Speed", UnitOfSpeed.METERS_PER_SECOND],
    "wind_direction": ["Wind Direction", ""],
    "wind_gust": ["Wind Gust", UnitOfSpeed.METERS_PER_SECOND],
    "humidity": ["Humidity", PERCENTAGE],
    "clouds": ["Cloud Coverage", PERCENTAGE],
    "rain": ["Rain", "mm/hr"],
    "forecast_time": ["Time", None],
    "time": ["Best Time Of Day", None],
}

SENSOR_LIGHTNING_TYPES = {
    "lightning": ["Lightning Strikes", None]
}

SENSOR_MAREO_TYPES = {
    "sea_level": ["Sea Level", "cm"]
}

PARALLEL_UPDATES = 1

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the FMI Sensor, including Best Time Of the Day sensor."""
    name = config_entry.data[CONF_NAME]
    lightning_mode = config_entry.options.get(CONF_LIGHTNING, False)

    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]

    entity_list = []

    for sensor_type in SENSOR_TYPES:
        entity_list.append(
            FMIBestConditionSensor(
                name, coordinator, sensor_type
            )
        )

    if lightning_mode:
        for sensor_type in SENSOR_LIGHTNING_TYPES:
            entity_list.append(
                FMILightningStrikesSensor(name, coordinator, sensor_type))

    for sensor_type in SENSOR_MAREO_TYPES:
        entity_list.append(
            FMIMareoSensor(name, coordinator, sensor_type))

    async_add_entities(entity_list, False)

def get_wind_direction_string(wind_direction_in_deg):
    """Get the string interpretation of wind direction in degrees"""

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
        else:
            return "Unavailable"

    return "Unavailable"


class FMIBestConditionSensor(CoordinatorEntity):
    """Implementation of a FMI Weather sensor with best conditions of the day."""

    def __init__(self, name, coordinator, sensor_type):
        """Initialize the sensor."""

        super().__init__(coordinator)
        self.client_name = name
        self._name = SENSOR_TYPES[sensor_type][0]
        self._fmi = coordinator
        self._state = None
        self._icon = None
        self.type = sensor_type
        self._unit_of_measurement = SENSOR_TYPES[sensor_type][1]

        self.update()

    @property
    def name(self):
        """Return the name of the sensor."""
        if self._fmi is not None:
            if self._fmi.current is not None:
                return f"{self._fmi.current.place} {self._name}"

        return self._name

    @property
    def unique_id(self):
        f"{self.coordinator.unique_id}_{self.name}"

    @property
    def state(self):
        """Return the state of the sensor."""

        self.update()
        return self._state

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def unit_of_measurement(self):
        """Return unit of measurement."""
        return self._unit_of_measurement

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self.type == "time":
            if self._fmi is not None:
                if self._fmi.current is not None:
                    return {
                        ATTR_LOCATION: self._fmi.current.place,
                        ATTR_TIME: self._fmi.best_time,
                        ATTR_TEMPERATURE: self._fmi.best_temperature,
                        ATTR_HUMIDITY: self._fmi.best_humidity,
                        ATTR_PRECIPITATION: self._fmi.best_precipitation,
                        ATTR_WIND_SPEED: self._fmi.best_wind_speed,
                        ATTR_ATTRIBUTION: ATTRIBUTION,
                    }

        return {ATTR_ATTRIBUTION: ATTRIBUTION}

    def update(self):
        """Get the latest data from FMI and updates the states."""
        if self._fmi is None:
            _LOGGER.debug("FMI: Coordinator is not available")
            return

        if self._fmi.current is None:
            _LOGGER.debug("FMI: Sensor _FMI Current Forecast is unavailable")
            return

        if self.type == "place":
            self._state = self._fmi.current.place
            self._icon = "mdi:city-variant"
            return

        source_data = None

        # Update the sensor states
        if self._fmi.time_step == 1:
            # Current weather
            source_data = self._fmi.current.data
        else:
            # Forecasted weather based on configured time_step - next forecasted hour, if available

            if self._fmi.forecast is None:
                _LOGGER.debug("FMI: Sensor _FMI Hourly Forecast is unavailable")
                return

            # If current time is half past or more then use the hour next to next hour
            # otherwise fallback to the next hour
            if len(self._fmi.forecast.forecasts) > 1:
                curr_min = datetime.now().minute
                if curr_min >= 30:
                    source_data = self._fmi.forecast.forecasts[1]
            else:
                source_data = self._fmi.forecast.forecasts[0]

        if source_data is None:
            _LOGGER.debug("FMI: Sensor Source data is unavailable")
            return

        wind_direction = "Unavailable"
        if source_data.wind_direction is not None:
            wind_direction = get_wind_direction_string(source_data.wind_direction.value)

        if self.type == "forecast_time":
            self._state = source_data.time.astimezone(tz.tzlocal())
            self._icon = "mdi:av-timer"
        elif self.type == "weather":
            self._state = get_weather_symbol(source_data.symbol.value)
        elif self.type == "temperature":
            self._state = source_data.temperature.value
            self._icon = "mdi:thermometer"
        elif self.type == "wind_speed":
            self._state = source_data.wind_speed.value
            self._icon = "mdi:weather-windy"
        elif self.type == "wind_direction":
            self._state = wind_direction
            self._icon = "mdi:weather-windy"
        elif self.type == "wind_gust":
            self._state = source_data.wind_gust.value
            self._icon = "mdi:weather-windy"
        elif self.type == "humidity":
            self._state = source_data.humidity.value
            self._icon = "mdi:water"
        elif self.type == "clouds":
            self._state = source_data.cloud_cover.value
            self._icon = "mdi:weather-cloudy"
        elif self.type == "rain":
            self._state = source_data.precipitation_amount.value
            self._icon = "mdi:weather-pouring"
        elif self.type == "time":
            self._state = self._fmi.best_state
            self._icon = "mdi:av-timer"
        else:
            self._state = None


class FMILightningStrikesSensor(CoordinatorEntity):
    """Implementation of a FMI Lightning strikes sensor."""

    def __init__(self, name, coordinator, sensor_type):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.client_name = name
        self._name = SENSOR_LIGHTNING_TYPES[sensor_type][0]
        self._state = None
        self._icon = "mdi:weather-lightning"
        self.type = sensor_type
        self._unit_of_measurement = SENSOR_LIGHTNING_TYPES[sensor_type][1]
        self._fmi = coordinator
        self.lightning_data = coordinator.lightning_data

        try:
            self._fmi_name = coordinator.current.place
        except:
            self._fmi_name = None

        self.update()

    @property
    def name(self):
        """Return the name of the sensor."""

        if self._fmi_name is not None:
            return f"{self._fmi_name} {self._name}"
        else:
            return f"{self.client_name} {self._name}"

    @property
    def state(self):
        """Return the state of the sensor."""

        self.update()
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self.lightning_data is None:
            return []

        if len(self.lightning_data) == 0:
            return []

        return {
            ATTR_LOCATION: self.lightning_data[0].location,
            ATTR_TIME: self.lightning_data[0].time,
            ATTR_DISTANCE: self.lightning_data[0].distance,
            ATTR_STRIKES: self.lightning_data[0].strikes,
            ATTR_PEAK_CURRENT: self.lightning_data[0].peak_current,
            ATTR_CLOUD_COVER: self.lightning_data[0].cloud_cover,
            ATTR_ELLIPSE_MAJOR: self.lightning_data[0].ellipse_major,
            "OBSERVATIONS": [
                {
                    ATTR_LOCATION: strike.location,
                    ATTR_TIME: strike.time,
                    ATTR_DISTANCE: strike.distance,
                    ATTR_STRIKES: strike.strikes,
                    ATTR_PEAK_CURRENT: strike.peak_current,
                    ATTR_CLOUD_COVER: strike.cloud_cover,
                    ATTR_ELLIPSE_MAJOR: strike.ellipse_major,
                }
                for strike in self.lightning_data[1:]
            ],
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

    def update(self):
        """Get the latest data from FMI and updates the states."""

        try:
            self._state = self.lightning_data[0].location
        except:
            _LOGGER.debug("FMI: Sensor Lightning is unavailable")
            self._state = "Unavailable"

        return


class FMIMareoSensor(CoordinatorEntity):
    """Implementation of a FMI sea water level sensor."""

    def __init__(self, name, coordinator, sensor_type):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.client_name = name
        self._name = SENSOR_MAREO_TYPES[sensor_type][0]
        self._state = None
        self._icon = "mdi:waves"
        self.type = sensor_type
        self._unit_of_measurement = SENSOR_MAREO_TYPES[sensor_type][1]
        self._fmi = coordinator

        try:
            self._fmi_name = coordinator.current.place
        except:
            self._fmi_name = None

        self.update()

    @property
    def name(self):
        """Return the name of the sensor."""

        if self._fmi_name is not None:
            return f"{self._fmi_name} {self._name}"
        else:
            return f"{self.client_name} {self._name}"

    @property
    def state(self):
        """Return the state of the sensor."""

        self.update()
        return self._state

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
    def extra_state_attributes(self):
        """Return the state attributes."""

        mareo_data = self._fmi.mareo_data.sea_levels

        if mareo_data is None:
            return []

        if len(mareo_data) > 1:
            pass
        elif len(mareo_data) > 0:
            return {
                ATTR_TIME: mareo_data[0][0],
                "FORECASTS": [],
                ATTR_ATTRIBUTION: ATTRIBUTION
            }
        else:
            return []

        return {
            ATTR_TIME: mareo_data[0][0],
            "FORECASTS": [
                {"time": item[0], "height": item[1]} for item in mareo_data[1:]
            ],
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

    def update(self):
        """Get the latest data from FMI and updates the states."""

        mareo_data = self._fmi.mareo_data.sea_levels

        try:
            self._state = mareo_data[0][1]
        except:
            _LOGGER.debug("FMI: Sensor Mareo is unavailable")
            self._state = "Unavailable"

        return
