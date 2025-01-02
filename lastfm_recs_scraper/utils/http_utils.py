from typing import Any, Dict, Union
from urllib.parse import urlparse

import requests
import requests.adapters
from urllib3.util import Retry

from lastfm_recs_scraper.utils.constants import (
    PERMITTED_LAST_FM_API_METHODS,
    PERMITTED_RED_API_ACTIONS,
)
from lastfm_recs_scraper.utils.logging_utils import get_custom_logger

_LOGGER = get_custom_logger(__name__)


# TODO: see if the seconds_between_api_calls should be removed since it isn't currently used
def initialize_api_client(
    base_api_url: str, max_api_call_retries: int, seconds_between_api_calls: int
) -> requests.Session:
    base_domain = urlparse(base_api_url).netloc
    s = requests.Session()
    retries = Retry(total=max_api_call_retries, backoff_factor=1.0)
    s.mount(base_domain, requests.adapters.HTTPAdapter(max_retries=retries))
    return s


# TODO: initialize reusable and configured requests singletons here.
# _RED_CLIENT = initialize_api_client(base_api_domain="https://redacted.sh", )
# _LASTFM_CLIENT = ...
# _MUSICBRAINZ_CLIENT = ...


def request_red_api(red_client: requests.Session, action: str, params: str) -> Union[Dict[str, Any], bytes]:
    """
    Helper function to hit the RED API with retries and rate-limits.
    Returns the JSON response payload on success, and throws an Exception after MAX_RED_API_RETRIES consecutive failures.
    """
    if action not in PERMITTED_RED_API_ACTIONS:
        raise ValueError(
            f"Unexpected/Non-permitted 'action' provided to redacted api helper: '{action}'. Allowed actions are: {PERMITTED_RED_API_ACTIONS}"
        )
    url = f"https://redacted.sh/ajax.php?action={action}&{params}"
    if action == "download":
        response = red_client.get(url)
        return response.content
    json_data = red_client.get(url)
    return json_data["response"]


# e.g. request_lastfm_api(method="album.getinfo", params="artist=Dr.+Octagon&album=Dr.+Octagonecologyst")
def request_lastfm_api(last_fm_client: requests.Session, method: str, api_key: str, params: str) -> Dict[str, Any]:
    """
    Helper function to hit the LastFM API with retries and rate-limits.
    Returns the JSON response payload on success, and throws an Exception after MAX_LASTFM_API_RETRIES consecutive failures.
    """
    if method not in PERMITTED_LAST_FM_API_METHODS:
        raise ValueError(
            f"Unexpected method provided to lastfm api helper. Expected either {PERMITTED_LAST_FM_API_METHODS}"
        )
    json_data = last_fm_client.get(
        url=f"http://ws.audioscrobbler.com/2.0/?method={method}&api_key={api_key}&{params}&format=json",
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
        raise ValueError(
            f"Unexpected entity-type provided to musicbrainze api helper. Expected either 'release-group' or 'release'."
        )
    inc_params = (
        "inc=artist-credits" if entity_type == "release-group" else "inc=artist-credits+media+labels+release-groups"
    )
    json_data = musicbrainz_client.get(
        url=f"http://musicbrainz.org/ws/2/{entity_type}/{mbid}?{inc_params}",
        headers={"Accept": "application/json"},
    )
    return json_data
