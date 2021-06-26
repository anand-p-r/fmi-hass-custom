"""Config flow for FMI (Finnish Meteorological Institute) integration."""

import fmi_weather_client as fmi_client
from fmi_weather_client.errors import ClientError, ServerError
import voluptuous as vol

from homeassistant import config_entries, core
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME, CONF_OFFSET
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from . import base_unique_id

from .const import (
    _LOGGER,
    FORECAST_OFFSET,
    CONF_MIN_HUMIDITY,
    CONF_MAX_HUMIDITY,
    CONF_MIN_TEMP,
    CONF_MAX_TEMP,
    CONF_MIN_WIND_SPEED,
    CONF_MAX_WIND_SPEED,
    CONF_MIN_PRECIPITATION,
    CONF_MAX_PRECIPITATION,
    CONF_DAILY_MODE,
    HUMIDITY_RANGE,
    TEMP_RANGE,
    WIND_SPEED,
    CONF_LIGHTNING,
)


async def validate_user_config(hass: core.HomeAssistant, data):
    """Validate input configuration for FMI.

    Data contains Latitude / Longitude provided by user or from
    HASS default configuration.
    """
    latitude = data[CONF_LATITUDE]
    longitude = data[CONF_LONGITUDE]

    errors = ""

    # Current Weather
    try:
        weather_data = await hass.async_add_executor_job(
            fmi_client.weather_by_coordinates, latitude, longitude
        )

        return {"place": weather_data.place, "err": ""}
    except ClientError as err:
        err_string = (
            "Client error with status "
            + str(err.status_code)
            + " and message "
            + err.message
        )
        errors = "client_connect_error"
        _LOGGER.error(err_string)
    except ServerError as err:
        err_string = (
            "Server error with status "
            + str(err.status_code)
            + " and message "
            + err.body
        )
        errors = "server_connect_error"
        _LOGGER.error(err_string)

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
                base_unique_id(user_input[CONF_LATITUDE], user_input[CONF_LONGITUDE])
            )
            self._abort_if_unique_id_configured()

            valid = await validate_user_config(self.hass, user_input)

            if valid.get("err", "") == "":
                return self.async_create_entry(title=valid["place"], data=user_input)

            errors["fmi"] = valid["err"]

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="FMI"): str,
                vol.Required(
                    CONF_LATITUDE, default=self.hass.config.latitude
                ): cv.latitude,
                vol.Required(
                    CONF_LONGITUDE, default=self.hass.config.longitude
                ): cv.longitude
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Options callback for FMI."""
        return FMIOptionsFlowHandler(config_entry)


class FMIOptionsFlowHandler(config_entries.OptionsFlow):
    """Config flow options for FMI."""

    def __init__(self, config_entry):
        """Initialize FMI options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        if user_input is not None:
            return self.async_create_entry(title="FMI Options", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                vol.Optional(CONF_OFFSET, default=1): vol.In(FORECAST_OFFSET),
                vol.Optional(CONF_MIN_HUMIDITY, default=self.config_entry.options.get(
                    CONF_MIN_HUMIDITY, 30)): vol.In(HUMIDITY_RANGE),
                vol.Optional(CONF_MAX_HUMIDITY, default=self.config_entry.options.get(
                    CONF_MAX_HUMIDITY, 70)): vol.In(HUMIDITY_RANGE),
                vol.Optional(CONF_MIN_TEMP, default=self.config_entry.options.get(
                        CONF_MIN_TEMP, 10)): vol.In(TEMP_RANGE),
                vol.Optional(CONF_MAX_TEMP, default=self.config_entry.options.get(
                        CONF_MAX_TEMP, 30)): vol.In(TEMP_RANGE),
                vol.Optional(CONF_MIN_WIND_SPEED, default=self.config_entry.options.get(
                        CONF_MIN_WIND_SPEED, 0)): vol.In(WIND_SPEED),
                vol.Optional(CONF_MAX_WIND_SPEED, default=self.config_entry.options.get(
                        CONF_MAX_WIND_SPEED, 25)): vol.In(WIND_SPEED),
                vol.Optional(CONF_MIN_PRECIPITATION, default=self.config_entry.options.get(
                        CONF_MIN_PRECIPITATION, 0.0)): cv.small_float,
                vol.Optional(CONF_MAX_PRECIPITATION, default=self.config_entry.options.get(
                    CONF_MAX_PRECIPITATION, 0.2)): cv.small_float,
                vol.Optional(CONF_DAILY_MODE, default=self.config_entry.options.get(
                    CONF_DAILY_MODE, False)): cv.boolean,
                vol.Optional(CONF_LIGHTNING, default=self.config_entry.options.get(
                    CONF_LIGHTNING, False)): cv.boolean,
                }
            )
        )
