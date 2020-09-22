# fmi-hass-custom

`fmi-hass-custom` is a Home Assistant custom component for weather and sensor platform. It uses [FMI's Open-Data](https://en.ilmatieteenlaitos.fi/open-data) as a source for current and forecasted meteorological data for a given location.

Currently following platforms are supported within Home Assistant:

  - [Sensor](#sensor)
  - [Weather](#weather)

## Installation

    1. Using a tool of choice open the directory (folder) for HA configuration (where you find configuration YAML file).
    2. If `custom_components` directory does not exist, create one.
    3. In the `custom_components` directory create a new folder called `fmi`.
    4. Download all the files from the this repository and place the files in the new directory created.
    5. Add configuration in configuration YAML file. Examples and description can be found in later sections.
    6. Restart Home Assistant

## Sensor

The sensor plaform checks for new data every 30 minutes. In addition to weather attributes, sensor also provides reverse geo-coded location for the given latitute/longitude as well as the best time of the day based on user preferences.

To add FMI sensor to a Home Assistant installation add the following to configuration YAML file:

```YAML
# Example configuration YAML entry
sensor:
  - platform: fmi
    name: FMI
    latitude: 1234567
    longitude: 1234567
    offset: 1
    min_temperature: 15
    max_temperature: 25
    min_relative_humidity: 35
    max_relative_humidity: 70
    min_wind_speed: 0.0
    max_wind_speed: 30.0
    min_precipitation: 0.0
    max_precipitation: 1.0
```

If latitude are longitude are not provided, it will be detected from the home latitude and longitude settings. The user preferred weather attributes (min_temperature, max_humidity etc) are used to compare the day's weather forecast and provide a relative best time for outdoor activity. If the conditions are not met, state of sensor (`_best_time_of_day`) will be "not_available". Other sensors (monitored weather conditions) include "condition", "temperature", "wind speed", "humidity", "clouds" and "rain".
Sensor includes lightning strike observations as well. State value of this sensor shows the closest location (reverse geocoded address or latitude/longitude), where the last lightning strike was observed along. Additionally it contains the number of strikes, peak current in kA, cloud coverage and ellipse major. Attributes also contain the last 5 lightning observations with reverse geocoded addresses. Data is pulled every 60secs.

```YAML
# Configuration Description
name:
  description: "Name of sensor."
  required: false
  type: string
  default: "FMI"
latitude:
  description: "Manually specify latitude. By default the value will be taken from the Home Assistant configuration."
  required: false
  type: float
  default: Provided by Home Assistant configuration
longitude:
  description: "Manually specify longitude. By default the value will be taken from the Home Assistant configuration."
  required: false
  type: float
  default: Provided by Home Assistant configuration
offset:
  description: "Hour offset for forecast. Accepted values are one of [0, 1, 2, 3, 4, 6, 8, 12, 24]."
  required: false
  type: integer
  default: "Defaults to 0 (Current weather)"
min_temperature:
  description: "Preferred minimum temperature in °C."
  required: false
  type: float
  default: "Defaults to 10°C"
max_temperature:
  description: "Preferred maximum temperature in °C."
  required: false
  type: float
  default: "Defaults to 30°C"
min_relative_humidity:
  description: "Preferred minimum relative humidity in %."
  required: false
  type: float
  default: "Defaults to 30%"
max_relative_humidity:
  description: "Preferred maximum relative humidity in %."
  required: false
  type: float
  default: "Defaults to 70%"
min_wind_speed:
  description: "Preferred minimum wind speed in m/s."
  required: false
  type: float
  default: "Defaults to 0m/s"
max_wind_speed:
  description: "Preferred maximum wind speed in m/s."
  required: false
  type: float
  default: "Defaults to 25m/s"
min_precipitation:
  description: "Preferred minimum precipitation in mm/hr."
  required: false
  type: float
  default: "Defaults to 0mm/hr"
max_precipitation:
  description: "Preferred maximum precipitation in mm/hr."
  required: false
  type: float
  default: "Defaults to 0.2mm/hr"
```
This platform is an alternative to [fmi weather](#weather) platform.

## Weather
To add FMI weather platform to a Home Assistant installation, add the following to configuration YAML file:

```YAML
# Example configuration YAML entry
weather:
  - platform: fmi
    name: FMI
    latitude: 1234567
    longitude: 1234567
    offset: 1
```

If latitude are longitude are not provided, it will be detected from the home latitude and longitude settings.

```YAML
# Configuration Description
name:
  description: "Name of weather entity."
  required: false
  type: string
  default: "FMI"
latitude:
  description: "Manually specify latitude. By default the value will be taken from the Home Assistant configuration."
  required: false
  type: float
  default: "Provided by Home Assistant configuration"
longitude:
  description: "Manually specify longitude. By default the value will be taken from the Home Assistant configuration."
  required: false
  type: float
  default: "Provided by Home Assistant configuration"
offset:
  description: "Hour offset for forecast. Accepted values are one of [1, 2, 3, 4, 6, 8, 12, 24]."
  required: false
  type: integer
  default: "Defaults to 1 (weather forecast every hour)"
```
This platform is an alternative to [fmi sensor](#sensor) platform.

## Original Author
Anand Radhakrishnan [@anand-p-r](https://github.com/anand-p-r)