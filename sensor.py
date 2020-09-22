"""Support for weather service from FMI (Finnish Meteorological Institute) for sensor platform."""

from datetime import datetime, timedelta
from dateutil import tz
import requests
import time

import xml.etree.ElementTree as ET
from geopy.distance import geodesic
from geopy.geocoders import Nominatim

# Import homeassistant platform dependencies
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_LOCATION,
    ATTR_TEMPERATURE,
    ATTR_TIME,
    SPEED_METERS_PER_SECOND,
    TEMP_CELSIUS,
    PERCENTAGE,
)
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

from .const import (
    ATTRIBUTION,
    DOMAIN,
    ATTR_HUMIDITY,
    ATTR_WIND_SPEED,
    ATTR_PRECIPITATION,
    MIN_TIME_BETWEEN_LIGHTNING_UPDATES,
    BASE_URL,
    LIGHTNING_LIMIT,
    LOGGER,
    ATTR_DISTANCE,
    ATTR_STRIKES,
    ATTR_PEAK_CURRENT,
    ATTR_CLOUD_COVER,
    ATTR_ELLIPSE_MAJOR
)

from . import get_weather_symbol

SENSOR_TYPES = {
    "place": ["Place", None],
    "weather": ["Condition", None],
    "temperature": ["Temperature", TEMP_CELSIUS],
    "wind_speed": ["Wind speed", SPEED_METERS_PER_SECOND],
    "humidity": ["Humidity", PERCENTAGE],
    "clouds": ["Cloud Coverage", PERCENTAGE],
    "rain": ["Rain", "mm/hr"],
    "forecast_time": ["Time", None],
    "time": ["Best Time Of Day", None],
}

SENSOR_LIGHTNING_TYPES = {
    "lightning": ["Lightning Strikes", None]
}


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the FMI Sensor, including Best Time Of the Day sensor."""
    if discovery_info is None:
        return

    entity_list = []

    if "data_key" not in discovery_info:
        return

    fmi_obj = hass.data[DOMAIN][discovery_info["data_key"]]

    for sensor_type in SENSOR_TYPES:
        entity_list.append(
            FMIBestConditionSensor(
                DOMAIN, fmi_obj, sensor_type
            )
        )

    for sensor_type in SENSOR_LIGHTNING_TYPES:
        entity_list.append(
            FMILightningStrikesSensor(fmi_obj.name, fmi_obj.latitude, fmi_obj.longitude, sensor_type))

    async_add_entities(entity_list, True)


class FMIBestConditionSensor(Entity):
    """Implementation of a FMI Weather sensor with best conditions of the day."""

    def __init__(self, name, fmi_object, sensor_type):
        """Initialize the sensor."""
        if fmi_object is not None:
            self.client_name = fmi_object.name
        else:
            self.client_name = name

        self._name = SENSOR_TYPES[sensor_type][0]
        self.fmi_object = fmi_object
        self._state = None
        self._icon = None
        self.type = sensor_type
        self._unit_of_measurement = SENSOR_TYPES[sensor_type][1]

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self.client_name} {self._name}"

    @property
    def state(self):
        """Return the state of the sensor."""
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
    def device_state_attributes(self):
        """Return the state attributes."""
        if self.type == "time":
            if self.fmi_object is not None:
                if self.fmi_object.current is not None:
                    return {
                        ATTR_LOCATION: self.fmi_object.current.place,
                        ATTR_TIME: self.fmi_object.best_time,
                        ATTR_TEMPERATURE: self.fmi_object.best_temperature,
                        ATTR_HUMIDITY: self.fmi_object.best_humidity,
                        ATTR_PRECIPITATION: self.fmi_object.best_precipitation,
                        ATTR_WIND_SPEED: self.fmi_object.best_wind_speed,
                        ATTR_ATTRIBUTION: ATTRIBUTION,
                    }

        return {ATTR_ATTRIBUTION: ATTRIBUTION}

    def update(self):
        """Get the latest data from FMI and updates the states."""
        if self.fmi_object is None:
            return

        self.fmi_object.update()

        if self.fmi_object.current is None:
            return

        if self.type == "place":
            self._state = self.fmi_object.current.place
            self._icon = "mdi:city-variant"
            return

        source_data = None

        # Update the sensor states
        if self.fmi_object.time_step == 0:
            # Current weather
            source_data = self.fmi_object.current.data
        else:
            # Forecasted weather based on configured time_step - next forecasted hour, if available

            if self.fmi_object.hourly is None:
                return

            # If current time is half past or more then use the hour next to next hour
            # otherwise fallback to the next hour
            if len(self.fmi_object.hourly.forecasts) > 1:
                curr_min = datetime.now().minute
                if curr_min >= 30:
                    source_data = self.fmi_object.hourly.forecasts[1]
            else:
                source_data = self.fmi_object.hourly.forecasts[0]

        if source_data is None:
            return

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
            self._state = self.fmi_object.best_state
            self._icon = "mdi:av-timer"
        else:
            self._state = None


class FMILightningStruct():

    def __init__(self, time_val=None, location=None, distance=None, strikes=None, peak_current=None, cloud_cover=None, ellipse_major=None):
        """Initialize the lightning parameters."""
        self.time = time_val
        self.location = location
        self.distance = distance
        self.strikes = strikes
        self.peak_current = peak_current
        self.cloud_cover = cloud_cover
        self.ellipse_major = ellipse_major


class FMILightningStrikesSensor(Entity):
    """Implementation of a FMI Lightning strikes sensor."""

    def __init__(self, name, latitude, longitude, sensor_type):
        """Initialize the sensor."""
        self.client_name = name
        self._name = SENSOR_LIGHTNING_TYPES[sensor_type][0]
        self.lat = latitude
        self.long = longitude
        self._state = None
        self._icon = "mdi:weather-lightning"
        self.type = sensor_type
        self._unit_of_measurement = SENSOR_LIGHTNING_TYPES[sensor_type][1]
        self.lightning_data = None


    ## Main update function to get data from FMI
    def update_lightning_strikes(self):
            loc_time_list = []
            home_cords = (self.lat, self.long)

            start_time = datetime.today() - timedelta(days=7)

            ## Format datetime to string accepted as path parameter in REST
            start_time = str(start_time).split(".")[0]
            start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            start_time = "starttime=" + str(start_time.date()) + "T" + str(start_time.time()) + "Z"

            base_url = BASE_URL + start_time + "&"

            ## Fetch data
            response = requests.get(base_url)

            root = ET.fromstring(response.content)

            for child in root.iter():
                if child.tag.find("positions") > 0:
                    clean_text = child.text.lstrip()
                    val_list = clean_text.split("\n")
                    for loc_indx, val in enumerate(val_list):
                        if val != "":
                            val_split = val.split(" ")
                            #val_split[0] --> latitude
                            #val_split[1] --> longitude
                            #val_split[2] --> epoch time
                            lightning_coords = (float(val_split[0]), float(val_split[1]))
                            distance = 0
                            try:
                                distance = geodesic(lightning_coords, home_cords).km
                            except:
                                LOGGER.info(f"Unable to find distance between {lightning_coords} and {home_cords}")
                            add_tuple = (val_split[0], val_split[1], val_split[2], distance, loc_indx)
                            loc_time_list.append(add_tuple)

                elif child.tag.find("doubleOrNilReasonTupleList") > 0:
                    clean_text = child.text.lstrip()
                    val_list = clean_text.split("\n")
                    for indx, val in enumerate(val_list):
                        if val != "":
                            val_split = val.split(" ")
                            #val_split[1] --> cloud_cover
                            #val_split[2] --> peak_current
                            #val_split[3] --> ellipse_major
                            exist_tuple = loc_time_list[indx]
                            if indx == exist_tuple[4]:
                                add_tuple = (exist_tuple[0], exist_tuple[1], exist_tuple[2], exist_tuple[3], val_split[0], val_split[1], val_split[2], val_split[3])
                                loc_time_list[indx] = add_tuple
                            else:
                                print("Record mismtach - aborting query!")
                                break

            ## First sort for closes entries and filter to limit
            loc_time_list = sorted(loc_time_list, key=(lambda item: item[3])) ## distance
            loc_time_list = loc_time_list[:LIGHTNING_LIMIT]

            ## Second Sort based on date
            loc_time_list = sorted(loc_time_list, key=(lambda item: item[2]), reverse=True)  ## date

            geolocator = Nominatim(user_agent="fmi_hassio_sensor")
            ## Reverse geocoding
            op_tuples = []
            for indx, v in enumerate(loc_time_list):
                loc = str(v[0]) + ", " + str(v[1])
                loc_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(v[2])))
                try:
                    location = geolocator.reverse(loc, language="en").address
                except:
                    LOGGER.info(f"Unable to reverse geocode for address-{loc}")
                    location = loc

                ## Time, Location, Distance, Strikes, Peak Current, Cloud Cover, Ellipse Major
                op = FMILightningStruct(time_val=loc_time, location=location, distance=v[3], strikes=v[4], peak_current=v[5], cloud_cover=v[6], ellipse_major=v[7])
                op_tuples.append(op)

            self.lightning_data = op_tuples

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self.client_name} {self._name}"

    @property
    def state(self):
        """Return the state of the sensor."""
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
    def device_state_attributes(self):
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
                    ATTR_ELLIPSE_MAJOR: strike.ellipse_major
                }
                for strike in self.lightning_data[1:]
            ],
            ATTR_ATTRIBUTION: ATTRIBUTION
        }

    @Throttle(MIN_TIME_BETWEEN_LIGHTNING_UPDATES)
    def update(self):
        """Get the latest data from FMI and update the states."""

        # Update lightning strike data
        self.update_lightning_strikes()

        try:
            self._state = self.lightning_data[0].location
        except:
            self._state = "Unavailable"

        return