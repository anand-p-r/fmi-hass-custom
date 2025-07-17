"""The FMI (Finnish Meteorological Institute) component."""

import typing
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import fmi_weather_client as fmi
import fmi_weather_client.models as fmi_models
import fmi_weather_client.errors as fmi_erros
import requests
from async_timeout import timeout
from dateutil import tz
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_OFFSET
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (DataUpdateCoordinator,
                                                      UpdateFailed)

from . import utils
from . import const


LOGGER = const._LOGGER
PLATFORMS = ["sensor", "weather"]


def base_unique_id(latitude, longitude):
    """Return unique id for entries in configuration."""
    return f"{latitude}_{longitude}"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up configured FMI."""
    hass.data.setdefault(const.DOMAIN, {})
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

    hass.data[const.DOMAIN][config_entry.entry_id] = {
        const.COORDINATOR: coordinator,
        const.UNDO_UPDATE_LISTENER: undo_listener,
    }

    await hass.config_entries.async_forward_entry_setups(
        config_entry,
        PLATFORMS
    )

    return True


async def async_unload_entry(hass, config_entry):
    """Unload an FMI config entry."""
    await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)

    hass.data[const.DOMAIN][config_entry.entry_id][const.UNDO_UPDATE_LISTENER]()
    hass.data[const.DOMAIN].pop(config_entry.entry_id)

    return True


async def update_listener(hass, config_entry):
    """Update FMI listener."""
    await hass.config_entries.async_reload(config_entry.entry_id)


class FMILightningStruct():

    def __init__(self, time_val=None, location=None, distance=None, strikes=None,
                 peak_current=None, cloud_cover=None, ellipse_major=None):
        """Initialize the lightning parameters."""
        self.time = time_val
        self.location = location
        self.distance = distance
        self.strikes = strikes
        self.peak_current = peak_current
        self.cloud_cover = cloud_cover
        self.ellipse_major = ellipse_major


class FMIMareoStruct():

    class SeaLevelData():
        def __init__(self, time_val: datetime, sea_level: float):
            """Initialize the sea level data."""
            self.time = time_val
            self.sea_level = sea_level

    def __init__(self):
        """Initialize the sea height data."""
        self.sea_levels: list[FMIMareoStruct.SeaLevelData] = []

    def size(self) -> int:
        """Get the size of the sea level data."""
        return len(self.sea_levels)

    def get_values(self) -> list[SeaLevelData]:
        """Get the sea level values."""
        return list(self.sea_levels)

    def append(self, sea_level_data: SeaLevelData):
        """Clear the sea level data."""
        self.sea_levels.append(sea_level_data)

    def append_values(self, time_val, sea_level):
        """Clear the sea level data."""
        sea_level_data = FMIMareoStruct.SeaLevelData(time_val, sea_level)
        self.sea_levels.append(sea_level_data)


class FMIDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching FMI data API."""

    def __init__(self, hass: HomeAssistant, session, config_entry):
        """Initialize."""

        LOGGER.debug("Using lat: %s and long: %s",
            config_entry.data[CONF_LATITUDE], config_entry.data[CONF_LONGITUDE])

        self._hass = hass

        self.latitude = config_entry.data[CONF_LATITUDE]
        self.longitude = config_entry.data[CONF_LONGITUDE]
        self.unique_id = str(self.latitude) + ":" + str(self.longitude)

        _options: dict = config_entry.options

        self.time_step = int(_options.get(CONF_OFFSET, const.FORECAST_OFFSET[0]))
        self.forecast_points = (
            int(_options.get(const.CONF_FORECAST_DAYS, const.DAYS_DEFAULT)
                ) * 24 // self.time_step)
        self.min_temperature = float(_options.get(const.CONF_MIN_TEMP, const.TEMP_MIN_DEFAULT))
        self.max_temperature = float(_options.get(const.CONF_MAX_TEMP, const.TEMP_MAX_DEFAULT))
        self.min_humidity = float(_options.get(const.CONF_MIN_HUMIDITY, const.HUMIDITY_MIN_DEFAULT))
        self.max_humidity = float(_options.get(const.CONF_MAX_HUMIDITY, const.HUMIDITY_MAX_DEFAULT))
        self.min_wind_speed = float(_options.get(const.CONF_MIN_WIND_SPEED, const.WIND_SPEED_MIN_DEFAULT))
        self.max_wind_speed = float(_options.get(const.CONF_MAX_WIND_SPEED, const.WIND_SPEED_MAX_DEFAULT))
        self.min_precip = float(_options.get(const.CONF_MIN_PRECIPITATION, const.PRECIPITATION_MIN_DEFAULT))
        self.max_precip = float(_options.get(const.CONF_MAX_PRECIPITATION, const.PRECIPITATION_MAX_DEFAULT))
        self.daily_mode = bool(_options.get(const.CONF_DAILY_MODE, const.DAILY_MODE_DEFAULT))
        self.lightning_mode = bool(_options.get(const.CONF_LIGHTNING, const.LIGHTNING_DEFAULT))
        self.lightning_radius = int(_options.get(const.CONF_LIGHTNING_DISTANCE,
                                                 const.BOUNDING_BOX_HALF_SIDE_KM))
        self.observation_enabled = bool(_options.get(const.CONF_OBSERVATION_EN, const.OBSERVATION_DEFAULT))

        self.current: typing.Optional[fmi_models.Weather] = None
        self.forecast: typing.Optional[fmi_models.Forecast] = None

        # Best Time Attributes derived based on forecast weather data
        self.best_time: typing.Optional[datetime] = None
        self.best_temperature: typing.Optional[float] = None
        self.best_humidity: typing.Optional[float] = None
        self.best_wind_speed: typing.Optional[float] = None
        self.best_precipitation: typing.Optional[float] = None
        self.best_state: typing.Optional[str] = None

        # Lightning strikes
        self.lightning_data: typing.Optional[list[FMILightningStruct]] = None

        # Mareo
        self.mareo_data: typing.Optional[FMIMareoStruct] = None

        min_update_time = const.MIN_TIME_BETWEEN_UPDATES

        LOGGER.debug("FMI: Data will be updated every %s min", min_update_time)

        super().__init__(hass, LOGGER, config_entry=config_entry,
                         name=const.DOMAIN, update_interval=min_update_time)

    def get_current(self):
        """Return the current weather data."""
        return self.current

    def get_current_place(self):
        """Return the current place."""
        if self.current is not None and hasattr(self.current, 'place'):
            return self.current.place
        return None

    async def _async_update_data(self):
        """Update data via Open API."""

        def update_best_weather_condition():
            if self.forecast is None:
                return

            if self.current is None:
                return

            curr_date = date.today()

            # Init values
            self.best_state = const.BEST_CONDITION_NOT_AVAIL
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
                    (forecast.symbol.value in const.BEST_COND_SYMBOLS)
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
                                self.best_state = const.BEST_CONDITION_AVAIL

                if self.best_state is const.BEST_CONDITION_AVAIL:
                    if forecast.temperature.value > self.best_temperature:
                        self.best_time = local_time
                        self.best_temperature = forecast.temperature.value
                        self.best_humidity = forecast.humidity.value
                        self.best_wind_speed = forecast.wind_speed.value
                        self.best_precipitation = forecast.precipitation_amount.value

        # Update lightning strike data
        def update_lightning_strikes():
            """Get the latest data from FMI and update the states."""

            LOGGER.debug("FMI: Lightning started")
            loc_time_list = []
            home_cords = (self.latitude, self.longitude)

            start_time = datetime.today() - timedelta(days=const.LIGHTNING_DAYS_LIMIT)

            ## Format datetime to string accepted as path parameter in REST
            start_time = str(start_time).split(".")[0]
            start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            start_time_uri_param = f"starttime={str(start_time.date())}T{str(start_time.time())}Z&"

            ## Get Bounding Box coords
            bbox_coords = utils.get_bounding_box(self.latitude, self.longitude, half_side_in_km=self.lightning_radius)
            bbox_uri_param = f"bbox={bbox_coords.lon_min},{bbox_coords.lat_min},{bbox_coords.lon_max},{bbox_coords.lat_max}&"

            base_url = const.BASE_URL + start_time_uri_param + bbox_uri_param
            LOGGER.debug(f"FMI: Lightning URI - {base_url}")

            ## Fetch data
            response = requests.get(base_url, timeout=const.TIMEOUT_LIGHTNING_PULL_IN_SECS)
            root = ET.fromstring(response.content)
            loop_timeout = time.time() + (const.LIGHTNING_LOOP_TIMEOUT_IN_SECS * 1000)
            for child in root.iter():
                if child.tag.find("positions") > 0:
                    clean_text = child.text.lstrip()
                    val_list = clean_text.split("\n")
                    num_locs = 0
                    for loc_index, val in enumerate(val_list):
                        if val != "":
                            val_split = val.split(" ")
                            lightning_coords = (float(val_split[0]), float(val_split[1]))
                            distance = 0
                            try:
                                distance = geodesic(lightning_coords, home_cords).km
                            except Exception:
                                LOGGER.info(f"Unable to find distance between {lightning_coords} and {home_cords}")

                            add_tuple = (val_split[0], val_split[1], val_split[2], distance, loc_index)
                            loc_time_list.append(add_tuple)
                            num_locs += 1

                            if time.time() > loop_timeout:
                                break

                elif child.tag.find("doubleOrNilReasonTupleList") > 0:
                    clean_text = child.text.lstrip()
                    val_list = clean_text.split("\n")
                    for index, val in enumerate(val_list):
                        if val != "":
                            val_split = val.split(" ")
                            exist_tuple = loc_time_list[index]
                            if index == exist_tuple[4]:
                                add_tuple = (exist_tuple[0], exist_tuple[1], exist_tuple[2], exist_tuple[3], val_split[0], val_split[1], val_split[2], val_split[3])
                                loc_time_list[index] = add_tuple

                                if time.time() > loop_timeout:
                                    break

                            else:
                                print("Record mismatch - aborting query")
                                break

            ## First sort for closes entries and filter to limit
            loc_time_list = sorted(loc_time_list, key=(lambda item: item[3])) ## distance
            LOGGER.debug(f"FMI - Coords retrieved for Lightning Data- {len(loc_time_list)}")

            loc_time_list = loc_time_list[:const.LIGHTNING_LIMIT]

            ## Second Sort based on date
            loc_time_list = sorted(loc_time_list, key=(lambda item: item[2]), reverse=True)  ## date

            geolocator = Nominatim(user_agent="fmi_hassio_sensor")

            ## Reverse geocoding
            op_tuples = []
            for v in loc_time_list:
                loc = str(v[0]) + ", " + str(v[1])
                loc_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(v[2])))
                try:
                    location = geolocator.reverse(loc, language="en").address
                except Exception as e:
                    LOGGER.info(f"Unable to reverse geocode for address-{loc}. Got error-{e}")
                    location = loc

                ## Time, Location, Distance, Strikes, Peak Current, Cloud Cover, Ellipse Major
                op = FMILightningStruct(time_val=loc_time, location=location, distance=v[3],
                                        strikes=v[4], peak_current=v[5], cloud_cover=v[6], ellipse_major=v[7])
                op_tuples.append(op)
            self.lightning_data = op_tuples
            LOGGER.debug("FMI: Lightning ended")

        # Update mareo data
        def update_mareo_data():
            """Get the latest mareograph forecast data from FMI and update the states."""

            LOGGER.debug("FMI: mareo started")
            ## Format datetime to string accepted as path parameter in REST
            start_time = datetime.today()
            start_time = str(start_time).split(".")[0]
            start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            start_time = "starttime=" + str(start_time.date()) + "T" + str(start_time.time()) + "Z"

            ## Format location to string accepted as path parameter in REST
            loc_string = "latlon=" + str(self.latitude) + "," + str(self.longitude)

            base_mareo_url = const.BASE_MAREO_FORC_URL + loc_string + "&" + start_time + "&"
            LOGGER.debug("FMI: Using Mareo URL: %s", base_mareo_url)

            ## Fetch data
            response_mareo = requests.get(base_mareo_url, timeout=const.TIMEOUT_MAREO_PULL_IN_SECS)

            root_mareo = ET.fromstring(response_mareo.content)

            self.mareo_data = mareo_data = FMIMareoStruct()

            for n in range(len(root_mareo)):
                try:
                    if root_mareo[n][0][2].text == 'SeaLevel':
                        mareo_data.append_values(root_mareo[n][0][1].text, root_mareo[n][0][3].text)
                    elif root_mareo[n][0][2].text == 'SeaLevelN2000':
                        continue
                    else:
                        LOGGER.debug("Sealevel forecast unsupported record: %s", root_mareo[n][0][2].text)
                        continue
                except Exception:
                    LOGGER.debug(f"Sealevel forecast records not in expected format for index - {n} of locstring - {loc_string}")

            if mareo_data.size():
                LOGGER.debug("FMI: Mareo data updated")
            else:
                LOGGER.debug("FMI: Mareo data not updated. No data available")
            return

        # do actual data fetching
        try:
            async with timeout(const.TIMEOUT_FMI_INTEG_IN_SEC):
                # Fetch current weather data
                weather_data = await fmi.async_weather_by_coordinates(self.latitude, self.longitude)

                if self.observation_enabled and weather_data and weather_data.place is not None \
                    and hasattr(fmi, 'async_observation_by_place'):
                    # Fetch observation data from closest station
                    LOGGER.debug(f"FMI: Fetching observation data for a place {weather_data.place}")
                    observation_data = await fmi.async_observation_by_place(weather_data.place)
                    if observation_data is not None:
                        weather_data = observation_data

                self.current = weather_data

                if self.forecast_points:
                    self.forecast = await fmi.async_forecast_by_coordinates(
                        self.latitude, self.longitude, self.time_step, self.forecast_points)

                # Update best time parameters
                await self._hass.async_add_executor_job(
                    update_best_weather_condition
                )
                LOGGER.debug("FMI: Best Conditions updated")

                # Update lightning strikes
                if self.lightning_mode and self.lightning_radius:
                    await self._hass.async_add_executor_job(
                        update_lightning_strikes
                    )
                    LOGGER.debug("FMI: Lightning Conditions updated")

                # Update mareograph data on sea level
                await self._hass.async_add_executor_job(
                    update_mareo_data
                )
                LOGGER.debug("FMI: Mareograph sea level data updated")

        except (fmi_erros.ClientError, fmi_erros.ServerError) as error:
            raise UpdateFailed(error) from error
        return {}
