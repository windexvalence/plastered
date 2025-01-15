from datetime import datetime, timedelta
from time import sleep
from typing import Any, Dict, Optional, Set, Tuple
from urllib.parse import urlparse

import requests
from urllib3.util import Retry

from plastered.config.config_parser import AppConfig
from plastered.run_cache.run_cache import RunCache
from plastered.utils.constants import (
    LFM_API_BASE_URL,
    MUSICBRAINZ_API_BASE_URL,
    NON_CACHED_RED_API_ENDPOINTS,
    PERMITTED_LFM_API_ENDPOINTS,
    PERMITTED_MUSICBRAINZ_API_ENDPOINTS,
    PERMITTED_RED_API_ENDPOINTS,
    RED_API_BASE_URL,
    RED_JSON_RESPONSE_KEY,
)
from plastered.utils.exceptions import RedClientSnatchException


# TODO: enabled logging for these classes without circular dependency
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
        valid_endpoints: Set[str],
        run_cache: RunCache,
        non_cached_endpoints: Optional[Set[str]] = {},
    ):
        self._max_api_call_retries = max_api_call_retries
        self._throttle_period = timedelta(seconds=seconds_between_api_calls)
        self._valid_endpoints = valid_endpoints
        self._run_cache = run_cache
        self._non_cached_endpoints = non_cached_endpoints

        # initialize _time_of_last_call to midnight of the current day
        init_time = datetime.now()
        self._time_of_last_call = datetime(
            year=init_time.year, month=init_time.month, day=init_time.day, hour=0, minute=0
        )
        self._base_domain = urlparse(base_api_url).netloc
        self._session = requests.Session()
        # TODO: verify whether this should have the prefix set as the base_domain, or f"https://{base_domain}".
        self._session.mount(
            self._base_domain,
            requests.adapters.HTTPAdapter(max_retries=Retry(total=max_api_call_retries, backoff_factor=1.0)),
        )

    # adopted from https://gist.github.com/johncadengo/0f54a9ff5b53d10024ed
    def _throttle(self) -> None:
        """
        Helper method which the subclasses will call prior to submitting an API request. Ensures we are throttling each client request.
        """
        time_since_last_call = datetime.now() - self._time_of_last_call
        if time_since_last_call < self._throttle_period:
            wait_seconds = (self._throttle_period - time_since_last_call).seconds
            sleep(wait_seconds)
        self._time_of_last_call = datetime.now()

    def _construct_cache_key(self, endpoint: str, params: str) -> Tuple[str, str, str]:
        """
        The universal cache key construction across all the ThrottleAPIClient subclasses. This simplifies
        the code while allowing each subclass instance to share the same cache instance without collisions due to
        their cache keys being distinguished by the self._base_domain key prefix.
        """
        return (self._base_domain, endpoint, params)

    def _read_from_run_cache(self, endpoint: str, params: str) -> Optional[Dict[str, Any]]:
        """
        Return the cached API response if one exists and is valid, otherwise return None.
        Raises a ValueError if the provided endpoint is not in self._valid_endpoints.
        """
        if endpoint not in self._valid_endpoints:
            raise ValueError(
                f"Invalid endpoint provided to {self.__class__.__name__}: '{endpoint}'. Valid endpoints are: {self._valid_endpoints}"
            )
        if endpoint in self._non_cached_endpoints:
            print(
                f"{self.__class__.__name__}: Skipping read from api cache. endpoint '{endpoint}' is categorized as non-cacheable: {endpoint in self._non_cached_endpoints}"
            )
            return None
        return self._run_cache.load_data_if_valid(
            cache_key=self._construct_cache_key(endpoint=endpoint, params=params),
            data_validator_fn=lambda x: isinstance(x, dict),
        )

    def _write_cache_if_enabled(self, endpoint: str, params: str, result_json: Dict[str, Any]) -> bool:
        if endpoint in self._non_cached_endpoints or not self._run_cache.enabled:
            print(
                f"{self.__class__.__name__}: Skipping write to api cache. Endpoint '{endpoint}' non-cacheable: {endpoint in self._non_cached_endpoints}"
            )
            return False
        return self._run_cache.write_data(
            cache_key=self._construct_cache_key(endpoint=endpoint, params=params),
            data=result_json,
        )


class RedAPIClient(ThrottledAPIBaseClient):
    """
    RED-specific Subclass of the ThrottledAPIBaseClient for interacting with the RED API.
    Retries limit and throttling period are configured from user config.
    """

    def __init__(self, app_config: AppConfig, run_cache: RunCache):
        super().__init__(
            base_api_url=RED_API_BASE_URL,
            max_api_call_retries=app_config.get_cli_option("red_api_retries"),
            seconds_between_api_calls=app_config.get_cli_option("red_api_seconds_between_calls"),
            valid_endpoints=PERMITTED_RED_API_ENDPOINTS,
            run_cache=run_cache,
            non_cached_endpoints=NON_CACHED_RED_API_ENDPOINTS,
        )
        self._session.headers.update({"Authorization": app_config.get_cli_option("red_api_key")})
        # Make sure there are no built-in request retries for snatching to prevent masking errors when using FL tokens.
        no_retries_adapter = requests.adapters.HTTPAdapter(max_retries=0)
        self._session.mount(f"{RED_API_BASE_URL}?action=download", no_retries_adapter)
        self._use_fl_tokens = app_config.get_cli_option("use_fl_tokens")
        self._tids_snatched_with_fl_tokens: Set[str] = set()

    def request_api(self, action: str, params: str) -> Dict[str, Any]:
        """
        Helper method to hit the RED API with retries and rate-limits.
        Returns the JSON response payload on success for all endpoints except 'download'.
        Successful requests to the 'download' endpoint will have a return type of `bytes`.
        Throws an Exception after `self.max_api_call_retries` consecutive failures.
        """
        # Sanity check endpoint then attempt reading from cache
        loaded_from_cache = self._read_from_run_cache(endpoint=action, params=params)
        if loaded_from_cache:
            return loaded_from_cache
        # Enforce request throttling
        self._throttle()
        # Once throttling requirements are met, continue with building and submitting the request
        url = f"{RED_API_BASE_URL}?action={action}&{params}"
        json_data = self._session.get(url=url).json()
        if RED_JSON_RESPONSE_KEY not in json_data:  # pragma: no cover
            raise Exception(f"RED response JSON missing expected '{RED_JSON_RESPONSE_KEY}' key. JSON: '{json_data}'")
        result_json = json_data[RED_JSON_RESPONSE_KEY]
        cache_write_success = self._write_cache_if_enabled(endpoint=action, params=params, result_json=result_json)
        print(f"{self.__class__.__name__}: api cache write status: {cache_write_success}")
        return result_json

    def snatch(self, tid: str, can_use_token_on_torrent: bool) -> bytes:
        """
        Dedicated method specifically for snatching from red and returning the
        response contents' bytes which may be written to a .torrent file.
        This is separated from the `request_api` method since there's addition logic for FL tokens, and since we
        don't want to enable response caching for download requests.
        """
        self._throttle()
        params = f"id={tid}"
        # Try using a FL token if the app is configured to do so and the API states a FL token is usable.
        # Fallback to non-FL download on error (i.e. out of tokens after API response, etc.)
        if self._use_fl_tokens and can_use_token_on_torrent:
            fl_snatch_failed = False
            fl_params = f"{params}&usetoken=1"
            try:
                response = self._session.get(url=f"{RED_API_BASE_URL}?action=download&{fl_params}")
                if response.status_code != 200:
                    fl_snatch_failed = True
            except Exception:
                fl_snatch_failed = True
            if not fl_snatch_failed:
                self._tids_snatched_with_fl_tokens.add(tid)
                return response.content
            self._throttle()
        response = self._session.get(url=f"{RED_API_BASE_URL}?action=download&{params}")
        if response.status_code != 200:
            raise RedClientSnatchException(f"Non-200 status code in response: {response.status_code}.")
        return response.content

    def tid_snatched_with_fl_token(self, tid: str) -> bool:
        return tid in self._tids_snatched_with_fl_tokens


class LFMAPIClient(ThrottledAPIBaseClient):
    """
    LFM-specific Subclass of the ThrottledAPIBaseClient for interacting with the LFM API.
    Retries limit and throttling period are configured from user config.
    """

    def __init__(self, app_config: AppConfig, run_cache: RunCache):
        super().__init__(
            base_api_url=LFM_API_BASE_URL,
            max_api_call_retries=app_config.get_cli_option("lfm_api_retries"),
            seconds_between_api_calls=app_config.get_cli_option("lfm_api_seconds_between_calls"),
            run_cache=run_cache,
            valid_endpoints=PERMITTED_LFM_API_ENDPOINTS,
        )
        # TODO: figure out how to redact this from logs
        self._api_key = app_config.get_cli_option("lfm_api_key")

    def request_api(self, method: str, params: str) -> Dict[str, Any]:
        """
        Helper function to hit the LFM API with retries and rate-limits.
        Returns the JSON response payload on success, and throws an Exception after max allowed consecutive failures.
        """
        # Sanity check endpoint then attempt reading from cache
        loaded_from_cache = self._read_from_run_cache(endpoint=method, params=params)
        if loaded_from_cache:
            return loaded_from_cache
        # Enforce request throttling
        self._throttle()
        # Once throttling requirements are met, continue with building and submitting the request
        json_data = self._session.get(
            url=f"{LFM_API_BASE_URL}?method={method}&api_key={self._api_key}&{params}&format=json",
            headers={"Accept": "application/json"},
        ).json()
        top_key = method.split(".")[0]
        result_json = json_data[top_key]
        cache_write_success = self._write_cache_if_enabled(endpoint=method, params=params, result_json=result_json)
        print(f"{self.__class__.__name__}: api cache write status: {cache_write_success}")
        return result_json


class MusicBrainzAPIClient(ThrottledAPIBaseClient):
    """
    MB-specific Subclass of the ThrottledAPIBaseClient for interacting with the MB API.
    Retries limit and throttling period are configured from user config.
    """

    def __init__(self, app_config: AppConfig, run_cache: RunCache):
        super().__init__(
            base_api_url=MUSICBRAINZ_API_BASE_URL,
            max_api_call_retries=app_config.get_cli_option("musicbrainz_api_max_retries"),
            seconds_between_api_calls=app_config.get_cli_option("musicbrainz_api_seconds_between_calls"),
            run_cache=run_cache,
            valid_endpoints=PERMITTED_MUSICBRAINZ_API_ENDPOINTS,
        )

    def request_api(self, entity_type: str, mbid: str) -> Dict[str, Any]:
        """
        Helper function to hit the MusicBrainz API with retries and rate-limits.
        Returns the JSON response payload on success.
        Throws an Exception after `self._max_api_call_retries` consecutive failures.
        """
        # Sanity check endpoint then attempt reading from cache
        loaded_from_cache = self._read_from_run_cache(endpoint=entity_type, params=mbid)
        if loaded_from_cache:
            return loaded_from_cache
        # Enforce request throttling
        self._throttle()
        # Once throttling requirements are met, continue with building and submitting the request
        inc_params = (
            "inc=artist-credits" if entity_type == "release-group" else "inc=artist-credits+media+labels+release-groups"
        )
        json_data = self._session.get(
            url=f"{MUSICBRAINZ_API_BASE_URL}{entity_type}/{mbid}?{inc_params}",
            headers={"Accept": "application/json"},
        ).json()
        cache_write_success = self._write_cache_if_enabled(endpoint=entity_type, params=mbid, result_json=json_data)
        print(f"{self.__class__.__name__}: api cache write status: {cache_write_success}")
        return json_data
