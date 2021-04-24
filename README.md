# fmi-hass-custom

`fmi-hass-custom` is a Home Assistant custom component for weather and sensor platform. It uses [FMI's Open-Data](https://en.ilmatieteenlaitos.fi/open-data) as a source for current and forecasted meteorological data for a given location. Data update frequency is hard-fixed at 30mins.

## Pre-Installation

Follow these instructions if an older version of the component was in use

    1. Remove all references of the sensor and weather platforms from configuration.yaml.
    2. Restart Home Assistant
    3. UI references could also be removed (or they could be the markers to correct when the integration is loaded again using steps below)
    4. Most importantly clear browser cache where the Home Assistant UI is accessed. Sometimes, the new integration does not show up without this step.
    
## Installation

    1. Using a tool of choice open the directory (folder) for HA configuration (where you find configuration YAML file).
    2. If `custom_components` directory does not exist, create one.
    3. In the `custom_components` directory create a new folder called `fmi`.
    4. Download all the files from the this repository and place the files in the new directory created.
    5. Restart Home Assistant
    6. Install integration from UI (Configuration --> Intergations --> + --> Search for fmi)
    7. Specify the latitude and longitude (default values are picked from the Home Assistant configuration)

## Weather and Sensors

In addition to the weather platform, default sensors include different weather conditions (temperature, humidity, wind speed, cloud coverage etc.), "best time of the day" (based on preferences), closest lightning strikes and sea wave height forecasts. Preferences for "best time of the day" can be tweaked by changing the values via UI ```(Configuration --> Integrations --> Finnish Meteorological Institute --> Options)```. For tracking the weather and sensors of another location follow steps 6-7 of ```Installation``` with the latitude and longitude of the location.

Based on the latitude and longitude, location name is derived by reverse geo-coding. Sensors are then grouped based on the derived location name. For e.g. ```weather.<place_name>```,  ```sensor.<place_name>_temperature```, ```sensor.<place_name>_humidity``` etc.

## Original Author
Anand Radhakrishnan [@anand-p-r](https://github.com/anand-p-r)
