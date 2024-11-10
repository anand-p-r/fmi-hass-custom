"""The FMI (Finnish Meteorological Institute) component."""

import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import fmi_weather_client as fmi
import requests
from async_timeout import timeout
from dateutil import tz
from fmi_weather_client.errors import ClientError, ServerError
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_OFFSET
from homeassistant.core import HomeAssistant
try:
    # HA 2024.11 and newer
    from homeassistant.core_config import Config
except ImportError:
    # HA 2024.10 and older
    from homeassistant.core import Config
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (DataUpdateCoordinator,
                                                      UpdateFailed)

from .const import (
    _LOGGER, BASE_MAREO_FORC_URL, BASE_URL, BEST_COND_SYMBOLS,
    BEST_CONDITION_AVAIL, BEST_CONDITION_NOT_AVAIL,
    LIGHTNING_DAYS_LIMIT, CONF_MAX_HUMIDITY,
    CONF_MAX_PRECIPITATION, CONF_MAX_TEMP, CONF_MAX_WIND_SPEED,
    CONF_MIN_HUMIDITY, CONF_MIN_PRECIPITATION, CONF_MIN_TEMP,
    CONF_MIN_WIND_SPEED, CONF_DAILY_MODE, COORDINATOR, DOMAIN, LIGHTNING_LIMIT,
    MIN_TIME_BETWEEN_UPDATES, TIMEOUT_FMI_INTEG_IN_SEC,
    TIMEOUT_LIGHTNING_PULL_IN_SECS, TIMEOUT_MAREO_PULL_IN_SECS,
    UNDO_UPDATE_LISTENER, BOUNDING_BOX_HALF_SIDE_KM,
    LIGHTNING_LOOP_TIMEOUT_IN_SECS, CONF_LIGHTNING,
)

from .utils import (
    get_bounding_box
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

    await hass.config_entries.async_forward_entry_setups(
        config_entry,
        PLATFORMS
    )

    return True


async def async_unload_entry(hass, config_entry):
    """Unload an FMI config entry."""
    await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)

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


class FMIMareoStruct():

    #def __init__(self, time_val=None, sea_level_now=None, sea_level_6hrs=None):
    def __init__(self, sea_levels=None):
        """Initialize the sea height data."""
        self.sea_levels = sea_levels


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
        self.daily_mode = bool(config_entry.options.get(CONF_DAILY_MODE, False))
        self.lightning_mode = bool(config_entry.options.get(CONF_LIGHTNING, False))
        
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

        # Mareo
        self.mareo_data = None

        _LOGGER.debug("FMI: Data will be updated every %s min", MIN_TIME_BETWEEN_UPDATES)

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

            _LOGGER.debug(f"FMI: Lightning started")
            loc_time_list = []
            home_cords = (self.latitude, self.longitude)

            start_time = datetime.today() - timedelta(days=LIGHTNING_DAYS_LIMIT)

            ## Format datetime to string accepted as path parameter in REST
            start_time = str(start_time).split(".")[0]
            start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            start_time_uri_param = f"starttime={str(start_time.date())}T{str(start_time.time())}Z&"

            ## Get Bounding Box coords
            bbox_coords = get_bounding_box(self.latitude, self.longitude, half_side_in_km=BOUNDING_BOX_HALF_SIDE_KM)
            bbox_uri_param = f"bbox={bbox_coords.lon_min},{bbox_coords.lat_min},{bbox_coords.lon_max},{bbox_coords.lat_max}&"

            base_url = BASE_URL + start_time_uri_param + bbox_uri_param
            _LOGGER.debug(f"FMI: Lightning URI - {base_url}")

            ## Fetch data
            response = requests.get(base_url, timeout=TIMEOUT_LIGHTNING_PULL_IN_SECS)
            root = ET.fromstring(response.content)
            loop_timeout = time.time() + (LIGHTNING_LOOP_TIMEOUT_IN_SECS*1000)
            for child in root.iter():
                if child.tag.find("positions") > 0:
                    clean_text = child.text.lstrip()
                    val_list = clean_text.split("\n")
                    num_locs = 0
                    for loc_indx, val in enumerate(val_list):
                        if val != "":
                            val_split = val.split(" ")
                            lightning_coords = (float(val_split[0]), float(val_split[1]))
                            distance = 0
                            try:
                                distance = geodesic(lightning_coords, home_cords).km
                            except:
                                _LOGGER.info(f"Unable to find distance between {lightning_coords} and {home_cords}")

                            add_tuple = (val_split[0], val_split[1], val_split[2], distance, loc_indx)
                            loc_time_list.append(add_tuple)
                            num_locs += 1
                            
                            if time.time() > loop_timeout:
                                break
                        
                elif child.tag.find("doubleOrNilReasonTupleList") > 0:
                    clean_text = child.text.lstrip()
                    val_list = clean_text.split("\n")
                    for indx, val in enumerate(val_list):
                        if val != "":
                            val_split = val.split(" ")
                            exist_tuple = loc_time_list[indx]
                            if indx == exist_tuple[4]:
                                add_tuple = (exist_tuple[0], exist_tuple[1], exist_tuple[2], exist_tuple[3], val_split[0], val_split[1], val_split[2], val_split[3])
                                loc_time_list[indx] = add_tuple

                                if time.time() > loop_timeout:
                                    break

                            else:
                                print("Record mismtach - aborting query!")
                                break

            ## First sort for closes entries and filter to limit
            loc_time_list = sorted(loc_time_list, key=(lambda item: item[3])) ## distance
            _LOGGER.debug(f"FMI - Coords retrieved for Lightning Data- {len(loc_time_list)}")

            loc_time_list = loc_time_list[:LIGHTNING_LIMIT]

            ## Second Sort based on date
            loc_time_list = sorted(loc_time_list, key=(lambda item: item[2]), reverse=True)  ## date

            geolocator = Nominatim(user_agent="fmi_hassio_sensor")

            ## Reverse geocoding
            loop_start_time = datetime.now()
            op_tuples = []
            for indx, v in enumerate(loc_time_list):
                loc = str(v[0]) + ", " + str(v[1])
                loc_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(v[2])))
                try:
                    location = geolocator.reverse(loc, language="en").address
                except Exception as e:
                    _LOGGER.info(f"Unable to reverse geocode for address-{loc}. Got error-{e}")
                    location = loc

                ## Time, Location, Distance, Strikes, Peak Current, Cloud Cover, Ellipse Major
                op = FMILightningStruct(time_val=loc_time, location=location, distance=v[3], strikes=v[4], peak_current=v[5], cloud_cover=v[6], ellipse_major=v[7])
                op_tuples.append(op)
            loop_end_time = datetime.now()
            self.lightning_data = op_tuples
            _LOGGER.debug(f"FMI: Lightning ended")

        # Update mareo data
        def update_mareo_data():
            """Get the latest mareograph forecast data from FMI and update the states."""

            _LOGGER.debug(f"FMI: mareo started")
            ## Format datetime to string accepted as path parameter in REST
            start_time = datetime.today()
            start_time = str(start_time).split(".")[0]
            start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            start_time = "starttime=" + str(start_time.date()) + "T" + str(start_time.time()) + "Z"

            ## Format location to string accepted as path parameter in REST
            loc_string = "latlon=" + str(self.latitude) + "," + str(self.longitude)

            base_mareo_url = BASE_MAREO_FORC_URL + loc_string + "&" + start_time + "&"
            _LOGGER.debug("FMI: Using Mareo url: %s", base_mareo_url)

            ## Fetch data
            response_mareo = requests.get(base_mareo_url, timeout=TIMEOUT_MAREO_PULL_IN_SECS)

            root_mareo = ET.fromstring(response_mareo.content)

            sealevel_tuple_list = []
            for n in range(len(root_mareo)):
                try:
                    if root_mareo[n][0][2].text == 'SeaLevel':
                        tuple_to_add = (root_mareo[n][0][1].text, root_mareo[n][0][3].text)
                        sealevel_tuple_list.append(tuple_to_add)
                    elif root_mareo[n][0][2].text == 'SeaLevelN2000':
                        continue
                    else:
                        _LOGGER.debug("Sealevel forecast unsupported record: %s", root_mareo[n][0][2].text)
                        continue
                except:
                    _LOGGER.debug(f"Sealevel forecast records not in expected format for index - {n} of locstring - {loc_string}")

            mareo_op = FMIMareoStruct(sea_levels=sealevel_tuple_list)
            self.mareo_data = mareo_op
            if len(sealevel_tuple_list) > 12:
                _LOGGER.debug("FMI: Mareo_data updated with data: %s %s", sealevel_tuple_list[0], sealevel_tuple_list[12])
            else:
                _LOGGER.debug("FMI: Mareo_data not updated. No data available!")

            _LOGGER.debug(f"FMI: mareo ended")
            return

        try:
            async with timeout(TIMEOUT_FMI_INTEG_IN_SEC):
                self.current = await fmi.async_weather_by_coordinates(self.latitude, self.longitude)
                self.forecast = await fmi.async_forecast_by_coordinates(self.latitude, self.longitude, self.time_step)

                # Update best time parameters
                await self._hass.async_add_executor_job(
                    update_best_weather_condition
                )
                _LOGGER.debug("FMI: Best Conditions updated!")

                # Update lightning strikes
                if self.lightning_mode:
                    await self._hass.async_add_executor_job(
                        update_lightning_strikes
                    )
                    _LOGGER.debug("FMI: Lightning Conditions updated!")

                # Update mareograph data on sea level
                await self._hass.async_add_executor_job(
                    update_mareo_data
                )
                _LOGGER.debug("FMI: Mareograph sea level data updated!")

        except (ClientError, ServerError) as error:
            raise UpdateFailed(error) from error
        return {}
