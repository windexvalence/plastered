from datetime import datetime, timedelta
from time import sleep
from typing import Any, Dict, Union
from urllib.parse import urlparse

import requests
from urllib3.util import Retry

from lastfm_recs_scraper.config.config_parser import AppConfig
from lastfm_recs_scraper.utils.constants import (
    LAST_FM_API_BASE_URL,
    MUSICBRAINZ_API_BASE_URL,
    PERMITTED_LAST_FM_API_METHODS,
    PERMITTED_MUSICBRAINZ_API_ENTITIES,
    PERMITTED_RED_API_ACTIONS,
    RED_API_BASE_URL,
)


class ThrottledAPIBaseClient:
    """
    Base class that wraps a distinct requests.Sesssion instance with retries and throttling.
    Subclasses for the various rest APIs are implemented with their own request construction
    and uniquely configurable retry and throttling parameters.
    """

    def __init__(
        self,
        base_api_url: str,
        max_api_call_retries: int,
        seconds_between_api_calls: int,
    ):
        self._based_api_url = base_api_url
        self._max_api_call_retries = max_api_call_retries
        self._throttle_period = timedelta(seconds=seconds_between_api_calls)
        self._time_of_last_call = datetime.min
        self._base_domain = urlparse(base_api_url).netloc
        self._session = requests.Session()
        self._session.mount(
            self._base_domain,
            requests.adapters.HTTPAdapter(max_retries=Retry(total=max_api_call_retries, backoff_factor=1.0)),
        )

    # adopted from https://gist.github.com/johncadengo/0f54a9ff5b53d10024ed
    def _throttle(self) -> None:
        """
        Helper method which the subclasses will call prior to submitting an API request. Ensures we are throttling each client request.
        """
        now = datetime.now()
        time_since_last_call = now - self._time_of_last_call
        time_left = self._throttle_period - time_since_last_call
        if time_left > timedelta(seconds=0):
            sleep(time_left.seconds)
            self._time_of_last_call = datetime.now()


class RedAPIClient(ThrottledAPIBaseClient):
    """
    RED-specific Subclass of the ThrottledAPIBaseClient for interacting with the RED API.
    Retries limit and throttling period are configured from user config.
    """

    def __init__(self, app_config: AppConfig):
        super().__init__(
            base_api_url=RED_API_BASE_URL,
            max_api_call_retries=app_config.get_cli_option("red_api_retries"),
            seconds_between_api_calls=app_config.get_cli_option("red_api_seconds_between_calls"),
        )
        # TODO: figure out how to redact this from logs
        self._session.headers.update({"Authorization": app_config.get_cli_option("red_api_key")})

    def request_api(self, action: str, params: str) -> Union[Dict[str, Any], bytes]:
        """
        Helper method to hit the RED API with retries and rate-limits.
        Returns the JSON response payload on success for all endpoints except 'download'.
        Successful requests to the 'download' endpoint will have a return type of `bytes`.
        Throws an Exception after `self.max_api_call_retries` consecutive failures.
        """
        # Enforce request throttling
        self._throttle()
        # Once throttling requirements are met, continue with building and submitting the request
        if action not in PERMITTED_RED_API_ACTIONS:
            raise ValueError(
                f"Unexpected/Non-permitted 'action' provided to redacted api helper: '{action}'. Allowed actions are: {PERMITTED_RED_API_ACTIONS}"
            )
        url = f"https://redacted.sh/ajax.php?action={action}&{params}"
        if action == "download":
            response = self._session.get(url=url)
            return response.content
        json_data = self._session.get(url=url).json()
        return json_data["response"]


class LastFMAPIClient(ThrottledAPIBaseClient):
    """
    LFM-specific Subclass of the ThrottledAPIBaseClient for interacting with the LFM API.
    Retries limit and throttling period are configured from user config.
    """

    def __init__(self, app_config: AppConfig):
        super().__init__(
            base_api_url=LAST_FM_API_BASE_URL,
            max_api_call_retries=app_config.get_cli_option("last_fm_api_retries"),
            seconds_between_api_calls=app_config.get_cli_option("last_fm_api_seconds_between_calls"),
        )
        # TODO: figure out how to redact this from logs
        self._api_key = app_config.get_cli_option("last_fm_api_key")

    def request_api(self, method: str, params: str) -> Dict[str, Any]:
        """
        Helper function to hit the LastFM API with retries and rate-limits.
        Returns the JSON response payload on success, and throws an Exception after MAX_LASTFM_API_RETRIES consecutive failures.
        """
        # Enforce request throttling
        self._throttle()
        # Once throttling requirements are met, continue with building and submitting the request
        if method not in PERMITTED_LAST_FM_API_METHODS:
            raise ValueError(
                f"Unexpected method provided to lastfm api helper. Expected either {PERMITTED_LAST_FM_API_METHODS}"
            )
        json_data = self._session.get(
            url=f"https://ws.audioscrobbler.com/2.0/?method={method}&api_key={self._api_key}&{params}&format=json",
            headers={"Accept": "application/json"},
        ).json()
        top_key = method.split(".")[0]
        return json_data[top_key]


class MusicBrainzAPIClient(ThrottledAPIBaseClient):
    """
    MB-specific Subclass of the ThrottledAPIBaseClient for interacting with the MB API.
    Retries limit and throttling period are configured from user config.
    """

    def __init__(self, app_config: AppConfig):
        super().__init__(
            base_api_url=MUSICBRAINZ_API_BASE_URL,
            max_api_call_retries=app_config.get_cli_option("musicbrainz_api_max_retries"),
            seconds_between_api_calls=app_config.get_cli_option("musicbrainz_api_seconds_between_calls"),
        )

    def request_api(self, entity_type: str, mbid: str) -> Dict[str, Any]:
        """
        Helper function to hit the MusicBrainz API with retries and rate-limits.
        Returns the JSON response payload on success.
        Throws an Exception after `self._max_api_call_retries` consecutive failures.
        """
        # Enforce request throttling
        self._throttle()
        # Once throttling requirements are met, continue with building and submitting the request
        if entity_type not in PERMITTED_MUSICBRAINZ_API_ENTITIES:
            raise ValueError(f"Unexpected entity-type provided to musicbrainze api helper. Expected 'release'.")
        inc_params = (
            "inc=artist-credits" if entity_type == "release-group" else "inc=artist-credits+media+labels+release-groups"
        )
        json_data = self._session.get(
            url=f"https://musicbrainz.org/ws/2/{entity_type}/{mbid}?{inc_params}",
            headers={"Accept": "application/json"},
        ).json()
        return json_data
