"""Config flow for FMI (Finnish Meteorological Institute) integration."""

import fmi_weather_client as fmi_client
import fmi_weather_client.errors as fmi_erros

import voluptuous as vol

from homeassistant import config_entries, core
import homeassistant.const as ha_const
from homeassistant.helpers import config_validation as cv

from . import base_unique_id
from . import const


async def validate_user_config(hass: core.HomeAssistant, data):
    """Validate input configuration for FMI.

    Data contains Latitude / Longitude provided by user or from
    HASS default configuration.
    """
    latitude = data[ha_const.CONF_LATITUDE]
    longitude = data[ha_const.CONF_LONGITUDE]

    errors = ""

    # Current Weather
    try:
        weather_data = await hass.async_add_executor_job(
            fmi_client.weather_by_coordinates, latitude, longitude
        )

        return {"place": weather_data.place, "err": ""}
    except fmi_erros.ClientError as err:
        err_string = (
            "Client error with status "
            + str(err.status_code)
            + " and message "
            + err.message
        )
        errors = "client_connect_error"
        const.LOGGER.error(err_string)
    except fmi_erros.ServerError as err:
        err_string = (
            "Server error with status "
            + str(err.status_code)
            + " and message "
            + err.body
        )
        errors = "server_connect_error"
        const.LOGGER.error(err_string)

    return {"place": "None", "err": errors}


class FMIConfigFlowHandler(config_entries.ConfigFlow, domain="fmi"):
    """Config flow handler for FMI."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        """Handle user step."""
        # Display an option for the user to provide Lat/Long for the integration
        errors = {}
        if user_input is not None:

            await self.async_set_unique_id(
                base_unique_id(user_input[ha_const.CONF_LATITUDE],
                               user_input[ha_const.CONF_LONGITUDE])
            )
            self._abort_if_unique_id_configured()

            valid = await validate_user_config(self.hass, user_input)

            if valid.get("err", "") == "":
                return self.async_create_entry(title=valid["place"], data=user_input)

            errors["fmi"] = valid["err"]

        data_schema = vol.Schema(
            {
                vol.Required(ha_const.CONF_NAME, default=const.DEFAULT_NAME): str,
                vol.Required(ha_const.CONF_LATITUDE,
                             default=self.hass.config.latitude): cv.latitude,
                vol.Required(ha_const.CONF_LONGITUDE,
                             default=self.hass.config.longitude): cv.longitude
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @core.callback
    def async_get_options_flow(config_entry):
        """Options callback for FMI."""
        _ = config_entry
        return FMIOptionsFlowHandler()


class FMIOptionsFlowHandler(config_entries.OptionsFlow):
    """Config flow options for FMI."""

    @property
    def config_entry(self):
        """Return the config entry linked to the current options flow."""
        return self.hass.config_entries.async_get_entry(self.handler)

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        _ = user_input
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        if user_input is not None:
            return self.async_create_entry(title="FMI Options", data=user_input)

        _options = self.config_entry.options

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Optional(const.CONF_FORECAST_DAYS,
                             default=_options.get(
                                 const.CONF_FORECAST_DAYS,
                                 const.DAYS_DEFAULT)): vol.In(const.DAYS_RANGE),
                vol.Optional(ha_const.CONF_OFFSET,
                             default=_options.get(
                                 ha_const.CONF_OFFSET,
                                 const.FORECAST_OFFSET[0])): vol.In(const.FORECAST_OFFSET),
                vol.Optional(const.CONF_MIN_HUMIDITY,
                             default=_options.get(
                                 const.CONF_MIN_HUMIDITY,
                                 const.HUMIDITY_MIN_DEFAULT)): vol.In(const.HUMIDITY_RANGE),
                vol.Optional(const.CONF_MAX_HUMIDITY,
                             default=_options.get(
                                 const.CONF_MAX_HUMIDITY,
                                 const.HUMIDITY_MAX_DEFAULT)): vol.In(const.HUMIDITY_RANGE),
                vol.Optional(const.CONF_MIN_TEMP,
                             default=_options.get(
                                 const.CONF_MIN_TEMP,
                                 const.TEMP_MIN_DEFAULT)): vol.In(const.TEMP_RANGE),
                vol.Optional(const.CONF_MAX_TEMP,
                             default=_options.get(
                                 const.CONF_MAX_TEMP,
                                 const.TEMP_MAX_DEFAULT)): vol.In(const.TEMP_RANGE),
                vol.Optional(const.CONF_MIN_WIND_SPEED,
                             default=_options.get(
                                 const.CONF_MIN_WIND_SPEED,
                                 const.WIND_SPEED_MIN_DEFAULT)): vol.In(const.WIND_SPEED),
                vol.Optional(const.CONF_MAX_WIND_SPEED,
                             default=_options.get(
                                 const.CONF_MAX_WIND_SPEED,
                                 const.WIND_SPEED_MAX_DEFAULT)): vol.In(const.WIND_SPEED),
                vol.Optional(const.CONF_MIN_PRECIPITATION,
                             default=_options.get(
                                 const.CONF_MIN_PRECIPITATION,
                                 const.PRECIPITATION_MIN_DEFAULT)): cv.small_float,
                vol.Optional(const.CONF_MAX_PRECIPITATION,
                             default=_options.get(
                                 const.CONF_MAX_PRECIPITATION,
                                 const.PRECIPITATION_MAX_DEFAULT)): cv.small_float,
                vol.Optional(const.CONF_DAILY_MODE,
                             default=_options.get(
                                 const.CONF_DAILY_MODE,
                                 const.DAILY_MODE_DEFAULT)): cv.boolean,
                vol.Optional(const.CONF_LIGHTNING,
                             default=_options.get(
                                 const.CONF_LIGHTNING,
                                 const.LIGHTNING_DEFAULT)): cv.boolean,
                vol.Optional(const.CONF_LIGHTNING_DISTANCE,
                             default=_options.get(
                                 const.CONF_LIGHTNING_DISTANCE,
                                 const.BOUNDING_BOX_HALF_SIDE_KM)): cv.positive_int,
                vol.Optional(const.CONF_OBSERVATION_STATION,
                             default=_options.get(
                                 const.CONF_OBSERVATION_STATION, 0)): cv.positive_int,
            })
        )
