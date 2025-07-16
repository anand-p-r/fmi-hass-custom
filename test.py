"""Common utilities for the FMI Weather and Sensor integrations."""

import math
import logging
from datetime import datetime, timedelta
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import requests
import xml.etree.ElementTree as ET


from const import (
    LIGHTNING_DAYS_LIMIT,
    LIGHTNING_LIMIT,
    BOUNDING_BOX_HALF_SIDE_KM,
    BASE_URL,
    TIMEOUT_LIGHTNING_PULL_IN_SECS
)

_LOGGER = logging.getLogger(__package__)


class BoundingBox(object):
    def __init__(self, *args, **kwargs):
        self.lat_min = None
        self.lon_min = None
        self.lat_max = None
        self.lon_max = None


def get_bounding_box(latitude_in_degrees, longitude_in_degrees, half_side_in_km):
    assert half_side_in_km > 0
    assert latitude_in_degrees >= -90.0 and latitude_in_degrees  <= 90.0
    assert longitude_in_degrees >= -180.0 and longitude_in_degrees <= 180.0

    lat = math.radians(latitude_in_degrees)
    lon = math.radians(longitude_in_degrees)

    radius  = 6371
    # Radius of the parallel at given latitude
    parallel_radius = radius*math.cos(lat)

    lat_min = lat - half_side_in_km/radius  
    lat_max = lat + half_side_in_km/radius
    lon_min = lon - half_side_in_km/parallel_radius
    lon_max = lon + half_side_in_km/parallel_radius
    rad2deg = math.degrees

    box = BoundingBox()
    box.lat_min = rad2deg(lat_min)
    box.lon_min = rad2deg(lon_min)
    box.lat_max = rad2deg(lat_max)
    box.lon_max = rad2deg(lon_max)

    return box


def update_lightning_strikes(latitude=None, longitude=None, url=BASE_URL, custom_url=None):
    """Get the latest data from FMI and update the states."""

    _LOGGER.debug("FMI: Lightning started")
    loc_time_list = []
    home_cords = (latitude, longitude)

    start_time = datetime.today() - timedelta(days=LIGHTNING_DAYS_LIMIT)

    ## Format datetime to string accepted as path parameter in REST
    start_time = str(start_time).split(".")[0]
    start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    start_time_uri_param = f"starttime={str(start_time.date())}T{str(start_time.time())}Z&"

    ## Get Bounding Box coords
    bbox_coords = get_bounding_box(latitude, longitude, half_side_in_km=BOUNDING_BOX_HALF_SIDE_KM)
    bbox_uri_param = f"bbox={bbox_coords.lon_min},{bbox_coords.lat_min},{bbox_coords.lon_max},{bbox_coords.lat_max}&"

    base_url = None
    if custom_url is None:
        base_url = BASE_URL + start_time_uri_param + bbox_uri_param
        _LOGGER.debug(f"FMI: Lightning URI - {base_url}")
    else:
        base_url = custom_url
        _LOGGER.debug(f"FMI: Lightning URI - Using custom URL - {base_url}")


    ## Fetch data
    loop_start_time = datetime.now()
    response = requests.get(base_url, timeout=TIMEOUT_LIGHTNING_PULL_IN_SECS)
    url_fetch_end = datetime.now()
    _LOGGER.debug(f"URL fetch time - {(url_fetch_end - loop_start_time).total_seconds()}s")

    loop_start_time = datetime.now()
    root = ET.fromstring(response.content)
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
                        _LOGGER.info(f"Unable to find distance between {lightning_coords} and {home_cords}")

                    add_tuple = (val_split[0], val_split[1], val_split[2], distance, loc_index)
                    loc_time_list.append(add_tuple)
                    num_locs += 1
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
                    else:
                        print("Record mismatch - aborting query")
                        break

    ## First sort for closes entries and filter to limit
    loc_time_list = sorted(loc_time_list, key=(lambda item: item[3])) ## distance

    url_fetch_end = datetime.now()
    _LOGGER.debug(f"Looping time - {(url_fetch_end - loop_start_time).total_seconds()}s")

    _LOGGER.debug(f"FMI - Coords retrieved for Lightning Data- {len(loc_time_list)}")
    
    loc_time_list = loc_time_list[:LIGHTNING_LIMIT]

    ## Second Sort based on date
    loc_time_list = sorted(loc_time_list, key=(lambda item: item[2]), reverse=True)  ## date

    geolocator = Nominatim(user_agent="fmi_hassio_sensor")
    
    ## Reverse geocoding
    for _, v in enumerate(loc_time_list):
        loc = str(v[0]) + ", " + str(v[1])
        try:
            geolocator.reverse(loc, language="en").address
        except Exception as e:
            _LOGGER.info(f"Unable to reverse geocode for address-{loc}. Got error-{e}")

    _LOGGER.debug("FMI: Lightning ended")
    return


if __name__ == "__main__":
    lat = 61.55289772079975
    lon = 23.78579634262166
    box = get_bounding_box(lat, lon, 750)
    print(f"&bbox={box.lon_min},{box.lat_min},{box.lon_max},{box.lat_max}&")
    print(f"for gmaps: {box.lat_min}, {box.lon_min}  {box.lat_max}, {box.lon_max}")

    lat = 61.14397219067582
    lon = 25.351877243169923
    update_lightning_strikes(latitude=lat, longitude=lon)
