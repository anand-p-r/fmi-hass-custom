"""Common utilities for the FMI Weather and Sensor integrations."""

import os
import sys
import logging
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import requests
from geopy.distance import geodesic
from geopy.geocoders import Nominatim

# Add parent to sys path for project file imports
sys.path.append(os.path.abspath(os.path.join(sys.path[0], "..")))

import const  # noqa: E402
import utils  # noqa: E402


_LOGGER = logging.getLogger(__package__)


def __lightning_strikes_postions(loc_list: list, text: str, home_cords: tuple):
    val_list = text.lstrip().split("\n")

    for loc_index, val in enumerate(val_list):
        if not val:
            continue

        val_split = val.split(" ")
        lightning_coords = (float(val_split[0]), float(val_split[1]))
        distance = 0

        try:
            distance = geodesic(lightning_coords, home_cords).km
        except Exception:
            _LOGGER.info("Unable to find distance between "
                         f"{lightning_coords} and {home_cords}")

        add_tuple = (val_split[0], val_split[1], val_split[2],
                     distance, loc_index)
        loc_list.append(add_tuple)


def __lightning_strikes_reasons_list(loc_list: list, text: str):
    val_list = text.lstrip().split("\n")

    for index, val in enumerate(val_list):
        if not val:
            continue

        val_split = val.split(" ")
        exist_tuple = loc_list[index]

        if index != exist_tuple[4]:
            _LOGGER.debug("Record mismatch - aborting query")
            break

        loc_list[index] = (exist_tuple[0], exist_tuple[1], exist_tuple[2],
                           exist_tuple[3], val_split[0], val_split[1],
                           val_split[2], val_split[3])


def update_lightning_strikes(latitude=None, longitude=None, custom_url=None):
    """Get the latest data from FMI and update the states."""

    _LOGGER.debug("FMI: Lightning started")
    loc_time_list = []
    home_cords = (latitude, longitude)

    start_time = datetime.today() - timedelta(days=const.LIGHTNING_DAYS_LIMIT)

    # Format datetime to string accepted as path parameter in REST
    start_time = str(start_time).split(".")[0]
    start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    start_time_uri_param = f"starttime={str(start_time.date())}T{str(start_time.time())}Z&"

    # Get Bounding Box coords
    bbox_coords = utils.get_bounding_box(latitude, longitude,
                                         half_side_in_km=const.BOUNDING_BOX_HALF_SIDE_KM)
    bbox_uri_param = "bbox=" \
        f"{bbox_coords.lon_min},{bbox_coords.lat_min},"\
        f"{bbox_coords.lon_max},{bbox_coords.lat_max}&"

    base_url = None
    if custom_url is None:
        base_url = const.LIGHTNING_GET_URL + start_time_uri_param + bbox_uri_param
        _LOGGER.debug(f"FMI: Lightning URI - {base_url}")
    else:
        base_url = custom_url
        _LOGGER.debug(f"FMI: Lightning URI - Using custom URL - {base_url}")

    # Fetch data
    loop_start_time = datetime.now()
    response = requests.get(base_url, timeout=const.TIMEOUT_LIGHTNING_PULL_IN_SECS)
    url_fetch_end = datetime.now()
    _LOGGER.debug(f"URL fetch time - {(url_fetch_end - loop_start_time).total_seconds()}s")

    loop_start_time = datetime.now()
    root = ET.fromstring(response.content)

    for child in root.iter():
        if child.tag.find("positions") > 0:
            __lightning_strikes_postions(loc_time_list, child.text, home_cords)

        elif child.tag.find("doubleOrNilReasonTupleList") > 0:
            __lightning_strikes_reasons_list(loc_time_list, child.text)

    # First sort for closes entries and filter to limit
    loc_time_list = sorted(loc_time_list, key=lambda item: item[3])

    url_fetch_end = datetime.now()
    _LOGGER.debug(f"Looping time - {(url_fetch_end - loop_start_time).total_seconds()}s")

    _LOGGER.debug(f"FMI - Coords retrieved for Lightning Data- {len(loc_time_list)}")

    loc_time_list = loc_time_list[:const.LIGHTNING_LIMIT]

    # Second Sort based on date
    loc_time_list = sorted(loc_time_list, key=(lambda item: item[2]), reverse=True)  # date

    geolocator = Nominatim(user_agent="fmi_hassio_sensor")

    # Reverse geocoding
    for _, v in enumerate(loc_time_list):
        loc = str(v[0]) + ", " + str(v[1])
        try:
            geolocator.reverse(loc, language="en").address
        except Exception as e:
            _LOGGER.info(f"Unable to reverse geocode for address-{loc}. Got error-{e}")

    _LOGGER.debug("FMI: Lightning ended")


if __name__ == "__main__":
    locations = [
        # (lat, lon) pairs
        (61.55289772079975, 23.78579634262166),
        (61.14397219067582, 25.351877243169923),
    ]

    box = utils.get_bounding_box(*locations[0], 750)
    _LOGGER.info(f"&bbox={box.lon_min},{box.lat_min},{box.lon_max},{box.lat_max}&")
    _LOGGER.info(f"for gmaps: {box.lat_min}, {box.lon_min}  {box.lat_max}, {box.lon_max}")

    update_lightning_strikes(latitude=locations[1][0], longitude=locations[1][1])
