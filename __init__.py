"""The FMI (Finnish Meteorological Institute) component."""

from datetime import date, datetime, timedelta

from async_timeout import timeout

import requests
import time
import xml.etree.ElementTree as ET
from geopy.distance import geodesic
from geopy.geocoders import Nominatim

from dateutil import tz
import fmi_weather_client as fmi
from fmi_weather_client.errors import ClientError, ServerError

from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_OFFSET,
    SUN_EVENT_SUNSET,
)
from homeassistant.core import Config, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    _LOGGER,
    COORDINATOR,
    DOMAIN,
    FMI_WEATHER_SYMBOL_MAP,
    MIN_TIME_BETWEEN_UPDATES,
    UNDO_UPDATE_LISTENER,
    CONF_MIN_HUMIDITY,
    CONF_MAX_HUMIDITY,
    CONF_MIN_TEMP,
    CONF_MAX_TEMP,
    CONF_MIN_WIND_SPEED,
    CONF_MAX_WIND_SPEED,
    CONF_MIN_PRECIPITATION,
    CONF_MAX_PRECIPITATION,
    BEST_CONDITION_AVAIL,
    BEST_CONDITION_NOT_AVAIL,
    BEST_COND_SYMBOLS,
    BASE_URL,
    LIGHTNING_LIMIT
)

PLATFORMS = ["sensor", "weather"]


def base_unique_id(latitude, longitude):
    """Return unique id for entries in configuration."""
    return f"{latitude}_{longitude}"


async def async_setup(hass: HomeAssistant, config: Config) -> bool:
    """Set up configured FMI."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass, config_entry) -> bool:
    """Set up FMI as config entry."""
    websession = async_get_clientsession(hass)

    coordinator = FMIDataUpdateCoordinator(
        hass, websession, config_entry
    )
    await coordinator.async_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    undo_listener = config_entry.add_update_listener(update_listener)

    hass.data[DOMAIN][config_entry.entry_id] = {
        COORDINATOR: coordinator,
        UNDO_UPDATE_LISTENER: undo_listener,
    }

    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(config_entry, component)
        )

    return True


async def async_unload_entry(hass, config_entry):
    """Unload an FMI config entry."""
    for component in PLATFORMS:
        await hass.config_entries.async_forward_entry_unload(config_entry, component)

    hass.data[DOMAIN][config_entry.entry_id][UNDO_UPDATE_LISTENER]()
    hass.data[DOMAIN].pop(config_entry.entry_id)

    return True


async def update_listener(hass, config_entry):
    """Update FMI listener."""
    await hass.config_entries.async_reload(config_entry.entry_id)


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


class FMIDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching FMI data API."""

    def __init__(self, hass, session, config_entry):
        """Initialize."""

        _LOGGER.debug("Using lat: %s and long: %s", 
            config_entry.data[CONF_LATITUDE], config_entry.data[CONF_LONGITUDE])

        self.latitude = config_entry.data[CONF_LATITUDE]
        self.longitude = config_entry.data[CONF_LONGITUDE]
        self.unique_id = str(self.latitude) + ":" + str(self.longitude)
        self.time_step = config_entry.options.get(CONF_OFFSET, 1)

        self.min_temperature = float(config_entry.options.get(CONF_MIN_TEMP, 10))
        self.max_temperature = float(config_entry.options.get(CONF_MAX_TEMP, 30))
        self.min_humidity = float(config_entry.options.get(CONF_MIN_HUMIDITY, 30))
        self.max_humidity = float(config_entry.options.get(CONF_MAX_HUMIDITY, 70))
        self.min_wind_speed = float(config_entry.options.get(CONF_MIN_WIND_SPEED, 0))
        self.max_wind_speed = float(config_entry.options.get(CONF_MAX_WIND_SPEED, 25))
        self.min_precip = float(config_entry.options.get(CONF_MIN_PRECIPITATION, 0.0))
        self.max_precip = float(config_entry.options.get(CONF_MAX_PRECIPITATION, 0.2))

        self.current = None
        self.forecast = None
        self._hass = hass

        # Best Time Attributes derived based on forecast weather data
        self.best_time = None
        self.best_temperature = None
        self.best_humidity = None
        self.best_wind_speed = None
        self.best_precipitation = None
        self.best_state = None

        # Lightning strikes
        self.lightning_data = None

        _LOGGER.debug("Data will be updated every %s min", MIN_TIME_BETWEEN_UPDATES)

        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=MIN_TIME_BETWEEN_UPDATES
        )

    async def _async_update_data(self):
        """Update data via Open API."""

        def update_best_weather_condition():
            if self.forecast is None:
                return

            if self.current is None:
                return

            curr_date = date.today()

            # Init values
            self.best_state = BEST_CONDITION_NOT_AVAIL
            self.best_time = self.current.data.time.astimezone(tz.tzlocal())
            self.best_temperature = self.current.data.temperature.value
            self.best_humidity = self.current.data.humidity.value
            self.best_wind_speed = self.current.data.wind_speed.value
            self.best_precipitation = self.current.data.precipitation_amount.value

            for forecast in self.forecast.forecasts:
                local_time = forecast.time.astimezone(tz.tzlocal())

                if local_time.day == curr_date.day + 1:
                    # Tracking best conditions for only this day
                    break

                if (
                    (forecast.symbol.value in BEST_COND_SYMBOLS)
                    and (forecast.wind_speed.value >= self.min_wind_speed)
                    and (forecast.wind_speed.value <= self.max_wind_speed)
                ):
                    if (
                        forecast.temperature.value >= self.min_temperature
                        and forecast.temperature.value <= self.max_temperature
                    ):
                        if (
                            forecast.humidity.value >= self.min_humidity
                            and forecast.humidity.value <= self.max_humidity
                        ):
                            if (
                                forecast.precipitation_amount.value >= self.min_precip
                                and forecast.precipitation_amount.value
                                <= self.max_precip
                            ):
                                # What more can you ask for?
                                # Compare with temperature value already stored and update if necessary
                                self.best_state = BEST_CONDITION_AVAIL

                if self.best_state is BEST_CONDITION_AVAIL:
                    if forecast.temperature.value > self.best_temperature:
                        self.best_time = local_time
                        self.best_temperature = forecast.temperature.value
                        self.best_humidity = forecast.humidity.value
                        self.best_wind_speed = forecast.wind_speed.value
                        self.best_precipitation = forecast.precipitation_amount.value

        # Update lightning strike data
        def update_lightning_strikes():
            """Get the latest data from FMI and update the states."""

            loc_time_list = []
            home_cords = (self.latitude, self.longitude)

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
                                _LOGGER.info(f"Unable to find distance between {lightning_coords} and {home_cords}")
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
                    _LOGGER.info(f"Unable to reverse geocode for address-{loc}")
                    location = loc

                ## Time, Location, Distance, Strikes, Peak Current, Cloud Cover, Ellipse Major
                op = FMILightningStruct(time_val=loc_time, location=location, distance=v[3], strikes=v[4], peak_current=v[5], cloud_cover=v[6], ellipse_major=v[7])
                op_tuples.append(op)

            self.lightning_data = op_tuples

            return

        try:
            async with timeout(10):
                self.current = await self._hass.async_add_executor_job(
                    fmi.weather_by_coordinates, self.latitude, self.longitude
                )
                self.forecast = await self._hass.async_add_executor_job(
                    fmi.forecast_by_coordinates,
                    self.latitude,
                    self.longitude,
                    self.time_step,
                )

                # Update best time parameters
                await self._hass.async_add_executor_job(
                    update_best_weather_condition
                )

                # Update lightning strikes
                await self._hass.async_add_executor_job(
                    update_lightning_strikes
                )
                

        except (ClientError, ServerError) as error:
            raise UpdateFailed(error) from error
        return {}


def get_weather_symbol(symbol, hass=None):
    """Get a weather symbol for the symbol value."""
    ret_val = ""
    if symbol in FMI_WEATHER_SYMBOL_MAP.keys():
        ret_val = FMI_WEATHER_SYMBOL_MAP[symbol]
        if hass is not None and ret_val == 1:  # Clear as per FMI
            today = date.today()
            sunset = get_astral_event_date(hass, SUN_EVENT_SUNSET, today)
            sunset = sunset.astimezone(tz.tzlocal())

            if datetime.now().astimezone(tz.tzlocal()) >= sunset:
                # Clear night
                ret_val = FMI_WEATHER_SYMBOL_MAP[0]
    return ret_val
