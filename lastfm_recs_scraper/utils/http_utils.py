import functools
from typing import Any, Dict

import requests
from urllib.parse import urlparse

import requests.adapters
from urllib3.util import Retry
from urllib.parse import urlparse

from utils.logging_utils import get_custom_logger


_LOGGER = get_custom_logger(__name__)


def initialize_api_client(base_api_url: str, max_api_call_retries: int, seconds_between_api_calls: int) -> requests.Session:
    base_domain = urlparse(base_api_url).netloc
    s = requests.Session()
    retries = Retry(total=max_api_call_retries, backoff_factor=1.0)
    s.mount(base_domain, requests.adapters.HTTPAdapter(max_retries=retries))
    return s

# TODO: initialize reusable and configured requests singletons here.
# _RED_CLIENT = initialize_api_client(base_api_domain="https://redacted.sh", )
# _LASTFM_CLIENT = ...
# _MUSICBRAINZ_CLIENT = ...


def api_call(api_client: requests.Session, exception_class: Exception):
    def api_call_decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                func(*args, **kwargs)
            except Exception:
                _LOGGER.exception(f"API call failed with exception")
                raise exception_class(f"API failure encountered")
            return func(*args, **kwargs)
        return wrapper


def request_red_api(red_client: requests.Session, action: str, params: str) -> Dict[str, Any]:
    """
    Helper function to hit the RED API with retries and rate-limits.
    Returns the JSON response payload on success, and throws an Exception after MAX_RED_API_RETRIES consecutive failures.
    """
    json_data = red_client.get(request_url=f"https://redacted.sh/ajax.php?action={action}&{params}")
    return json_data["response"]


# e.g. request_lastfm_api(method="album.getinfo", params="artist=Dr.+Octagon&album=Dr.+Octagonecologyst")
def request_lastfm_api(last_fm_client: requests.Session, method: str, api_key: str, params: str) -> Dict[str, Any]:
    """
    Helper function to hit the LastFM API with retries and rate-limits.
    Returns the JSON response payload on success, and throws an Exception after MAX_LASTFM_API_RETRIES consecutive failures.
    """
    if method not in ["album.getinfo", "track.getinfo"]:
        raise ValueError(f"Unexpected method provided to lastfm api helper. Expected either 'album.getinfo' or 'track.getinfo'")
    json_data = last_fm_client.get(
        request_url=f"http://ws.audioscrobbler.com/2.0/?method={method}&api_key={api_key}&{params}&format=json",
        headers={"Accept": "application/json"},
    )
    top_key = method.split(".")[0]
    return json_data[top_key]


def request_musicbrainz_api(musicbrainz_client: requests.Session, entity_type: str, mbid: str) -> Dict[str, Any]:
    """
    Helper function to hit the MusicBrainz API with retries and rate-limits.
    Returns the JSON response payload on success, and throws an Exception after MAX_MUSICBRAINZ_API_RETRIES consecutive failures.
    """
    if entity_type not in ["release-group", "release"]:
        raise ValueError(f"Unexpected entity-type provided to musicbrainze api helper. Expected either 'release-group' or 'release'.")
    inc_params = "inc=artist-credits" if entity_type == "release-group" else "inc=artist-credits+media+labels+release-groups"
    json_data = musicbrainz_client.get(
        request_url=f"http://musicbrainz.org/ws/2/{entity_type}/{mbid}?{inc_params}",
        headers={"Accept": "application/json"},
    )
    return json_data
