import logging
from datetime import datetime, timedelta
from time import perf_counter_ns
from typing import Any, Dict, Optional, Set, Tuple
from urllib.parse import quote

import httpx
from tenacity import Retrying, wait_exponential

from plastered.config.config_parser import AppConfig
from plastered.run_cache.run_cache import RunCache
from plastered.utils.constants import (
    LFM_API_BASE_URL,
    MUSICBRAINZ_API_BASE_URL,
    NON_CACHED_RED_API_ENDPOINTS,
    NON_CACHED_RED_SNATCH_API_ENDPOINTS,
    PERMITTED_LFM_API_ENDPOINTS,
    PERMITTED_MUSICBRAINZ_API_ENDPOINTS,
    PERMITTED_RED_API_ENDPOINTS,
    PERMITTED_RED_SNATCH_API_ENDPOINTS,
    RED_API_BASE_URL,
    RED_JSON_RESPONSE_KEY,
)
from plastered.utils.exceptions import LFMClientException, RedClientSnatchException

_LOGGER = logging.getLogger(__name__)
_NANOSEC_TO_SEC = 1e9


# https://stackoverflow.com/a/74247651
def precise_delay(sec_delay: int) -> None:
    """
    A helper function that handles more precise waits for throttled API client calls.
    time.sleep can be inaccurate depending on the OS, and we need accuracy to avoid hitting rate limits.
    Adopts the recommended approach here: https://stackoverflow.com/a/74247651
    """
    target = perf_counter_ns() + sec_delay * _NANOSEC_TO_SEC
    while perf_counter_ns() < target:
        pass


# TODO: implement, and keep in mind the differences from requests library and httpx listed in  the link below:
# https://www.python-httpx.org/compatibility/


class HTTPXRetryTransport(httpx.BaseTransport):
    """
    Custom implementation of the `httpx.BaseTransport` class specifically for handling rate-limited request retries.
    This class is used as the underlying httpx transport for all the `ThrottledAPIBaseClient` classes.
    """

    def __init__(self, max_retries: int):
        self._max_retries = max_retries
        self._transport = httpx.HTTPTransport()

    # NOTE: non-decorated tenacity retry logic which resets per-call to handle_request was adopted
    # from this SO answer: https://stackoverflow.com/a/62238110
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        for attempt in Retrying(stop=wait_exponential(self._max_retries), reraise=True):
            with attempt:
                _LOGGER.debug(f"Handling request attempt number: {attempt.retry_state.attempt_number} ...")
                response = self._transport.handle_request(request)
        return response


class ThrottledAPIBaseClient:
    """
    Base class that wraps a distinct httpx.Client instance with retries and throttling.
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
        extra_client_transport_mount_entries: Optional[Dict[str, httpx.BaseTransport]] = {},
    ):
        self._max_api_call_retries = max_api_call_retries
        self._throttle_period = timedelta(seconds=seconds_between_api_calls)
        self._valid_endpoints = valid_endpoints
        self._run_cache = run_cache
        self._non_cached_endpoints = non_cached_endpoints
        self._extra_client_transport_mount_entries = extra_client_transport_mount_entries

        # initialize _time_of_last_call to midnight of the current day
        init_time = datetime.now()
        self._time_of_last_call = datetime(
            year=init_time.year, month=init_time.month, day=init_time.day, hour=0, minute=0
        )
        self._base_domain = base_api_url
        # TODO: rename the _session attribute and methods with "session" in name to "client"
        self._session = httpx.Client(
            mounts={self._base_domain: HTTPXRetryTransport(max_retries=self._max_api_call_retries)}
            | self._extra_client_transport_mount_entries,
            follow_redirects=True,
        )

    # Too much of a pain in the ass to write a test for
    def close_session(self) -> None:  # pragma: no cover
        if self._session:
            self._session.close()

    # adopted from https://gist.github.com/johncadengo/0f54a9ff5b53d10024ed
    def _throttle(self) -> None:
        """
        Helper method which the subclasses will call prior to submitting an API request. Ensures we are throttling each client request.
        """

        time_since_last_call = datetime.now() - self._time_of_last_call
        if time_since_last_call < self._throttle_period:
            wait_seconds = (self._throttle_period - time_since_last_call).seconds
            precise_delay(sec_delay=wait_seconds)
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
            _LOGGER.debug(
                f"{self.__class__.__name__}: Skipping read from api cache. endpoint '{endpoint}' is categorized as non-cacheable: {endpoint in self._non_cached_endpoints}"
            )
            return None
        return self._run_cache.load_data_if_valid(
            cache_key=self._construct_cache_key(endpoint=endpoint, params=params),
            data_validator_fn=lambda x: isinstance(x, dict),
        )

    def _write_cache_if_enabled(self, endpoint: str, params: str, result_json: Dict[str, Any]) -> bool:
        if endpoint in self._non_cached_endpoints or not self._run_cache.enabled:
            _LOGGER.debug(
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
        _LOGGER.debug(f"{self.__class__.__name__}: api cache write status: {cache_write_success}")
        return result_json


class RedSnatchAPIClient(ThrottledAPIBaseClient):
    """
    RED client specifically for snatch requests, which have unique constraints best encapsulated in a purpose built
    class, rather than pushing into the standard RED json API client class (`RedAPIClient`).

    Also contains some specialized logic for intelligently estimating the FL tokens available.
    """

    def __init__(self, app_config: AppConfig, run_cache: RunCache):
        super().__init__(
            base_api_url=RED_API_BASE_URL,
            # NOTE: the RedSnatchAPIClient doesn't use retries, so this is ignored
            max_api_call_retries=app_config.get_cli_option("red_api_retries"),
            seconds_between_api_calls=app_config.get_cli_option("red_api_seconds_between_calls"),
            valid_endpoints=PERMITTED_RED_SNATCH_API_ENDPOINTS,
            run_cache=run_cache,
            non_cached_endpoints=NON_CACHED_RED_SNATCH_API_ENDPOINTS,
            # This class overrides the internal default super class routing, to make sure
            # there are no built-in request retries for snatching to prevent masking errors when using FL tokens.
            extra_client_transport_mount_entries={RED_API_BASE_URL: httpx.HTTPTransport()},
        )
        self._session.headers.update({"Authorization": app_config.get_cli_option("red_api_key")})
        self._available_fl_tokens = 0
        self._use_fl_tokens = app_config.get_cli_option("use_fl_tokens")
        self._tids_snatched_with_fl_tokens: Set[str] = set()

    def set_initial_available_fl_tokens(self, initial_available_fl_tokens: int) -> None:
        self._available_fl_tokens = initial_available_fl_tokens
        if self._use_fl_tokens and self._available_fl_tokens == 0:
            _LOGGER.warning(f"Currently have zero RED FL tokens available. Ignoring 'use_fl_tokens' config setting.")
            self._use_fl_tokens = False

    def snatch(self, tid: str, can_use_token: bool) -> bytes:
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
        if self._use_fl_tokens and can_use_token and self._available_fl_tokens > 0:
            fl_snatch_failed = False
            fl_params = f"{params}&usetoken=1"
            try:
                response = self._session.get(url=f"{RED_API_BASE_URL}?action=download&{fl_params}")
                if response.is_error:
                    fl_snatch_failed = True
            except Exception:  # pragma: no cover
                fl_snatch_failed = True
            if not fl_snatch_failed:
                self._tids_snatched_with_fl_tokens.add(tid)
                self._available_fl_tokens -= 1
                return response.content
            self._throttle()
        response = self._session.get(url=f"{RED_API_BASE_URL}?action=download&{params}")
        if response.is_error:
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
        lfm_response = self._session.get(
            url=f"{LFM_API_BASE_URL}?method={method}&api_key={self._api_key}&{params}&format=json",
            headers={"Accept": "application/json"},
        )
        if lfm_response.is_error:
            raise LFMClientException(
                f"Unexpected LFM API error encountered for method '{method}' and params '{params}'. Status code: {lfm_response.status_code}"
            )
        json_data = lfm_response.json()
        # LMF API does non-standard stuff with surfacing errors sometimes.
        if "error" in json_data:
            raise LFMClientException(f"LFM API error encounterd. LFM error code: '{json_data['error']}'")
        top_key = method.split(".")[0]
        result_json = json_data[top_key]
        cache_write_success = self._write_cache_if_enabled(endpoint=method, params=params, result_json=result_json)
        _LOGGER.debug(f"{self.__class__.__name__}: api cache write status: {cache_write_success}")
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
        self._recording_endpoint = "recording"
        self._release_endpoint = "release"

    def request_release_details(self, mbid: str) -> Dict[str, Any]:
        """
        Helper method to hit the MusicBrainz release API with retries and rate-limits.
        Returns the JSON response payload on success.
        Throws an Exception after `self._max_api_call_retries` consecutive failures.
        """
        # Sanity check endpoint then attempt reading from cache
        loaded_from_cache = self._read_from_run_cache(endpoint=self._release_endpoint, params=mbid)
        if loaded_from_cache:
            return loaded_from_cache
        # Enforce request throttling
        self._throttle()
        # Once throttling requirements are met, continue with building and submitting the request
        inc_params = "inc=artist-credits+media+labels+release-groups"
        json_data = self._session.get(
            url=f"{MUSICBRAINZ_API_BASE_URL}{self._release_endpoint}/{mbid}?{inc_params}",
            headers={"Accept": "application/json"},
        ).json()
        cache_write_success = self._write_cache_if_enabled(
            endpoint=self._release_endpoint, params=mbid, result_json=json_data
        )
        _LOGGER.debug(f"{self.__class__.__name__}: api cache write status: {cache_write_success}")
        return json_data

    def _get_track_search_query_str(
        self,
        human_readable_track_name: str,
        artist_mbid: Optional[str] = None,
        human_readable_artist_name: Optional[str] = None,
    ) -> Optional[str]:
        search_query_prefix = f"recording:{quote(human_readable_track_name + ' AND ')}"
        if artist_mbid:
            return search_query_prefix + f"arid:{artist_mbid}"
        if human_readable_artist_name:
            return search_query_prefix + f"artist:{quote(human_readable_artist_name)}"
        _LOGGER.debug(
            f"Cannot resolve origin release for track rec: '{human_readable_track_name}'. No available artist_mbid or human readable artist name provided."
        )
        return None

    def request_release_details_for_track(
        self,
        human_readable_track_name: str,
        artist_mbid: Optional[str] = None,
        human_readable_artist_name: Optional[str] = None,
    ) -> Optional[Dict[str, Optional[str]]]:
        """
        Helper method specifically for attempting to resolve a release name / MBID from which a track rec originated from
        with retries and rate-limits. The underlying "endpoint" this method requests is MusicBrainz's "recording" search endpoint:
        https://musicbrainz.org/doc/MusicBrainz_API/Search#Recording
        This will only be called if the LFM API does not have a release name already associated with the track rec in question.

        If the origin release name cannot be resolved, returns None since the release name is required for searching on RED.
        Otherwise returns a dict of the the form {"origin_release_mbid": Optional[str], "origin_release_name": Optional[str]}
        """
        _LOGGER.debug(f"Attempting to resolve origin release for track rec: track: '{human_readable_track_name}' ...")
        search_query_str = self._get_track_search_query_str(
            human_readable_track_name=human_readable_track_name,
            artist_mbid=artist_mbid,
            human_readable_artist_name=human_readable_artist_name,
        )
        if not search_query_str:
            return None
        # Sanity check endpoint then attempt reading from cache
        loaded_from_cache = self._read_from_run_cache(endpoint=self._recording_endpoint, params=search_query_str)
        if loaded_from_cache:
            return loaded_from_cache
        # Enforce request throttling
        self._throttle()
        # Once throttling requirements are met, continue with building and submitting the request
        json_data = self._session.get(
            url=f"{MUSICBRAINZ_API_BASE_URL}{self._recording_endpoint}?query={search_query_str}&fmt=json",
            headers={"Accept": "application/json"},
        ).json()
        try:
            first_release_match_json = json_data["recordings"][0]["releases"][0]
        except (KeyError, IndexError):
            _LOGGER.debug(
                f"Unable to resolve an origin release for track: '{human_readable_track_name}' by '{human_readable_artist_name}'"
            )
            return None
        rel_mbid, rel_name = first_release_match_json.get("id"), first_release_match_json.get("title")
        if not rel_name:
            _LOGGER.debug(
                f"Unable to resolve origin release title for track: '{human_readable_track_name}' by '{human_readable_artist_name}'"
            )
            return None
        release_details = {"origin_release_mbid": rel_mbid, "origin_release_name": rel_name}
        cache_write_success = self._write_cache_if_enabled(
            endpoint=self._recording_endpoint, params=search_query_str, result_json=release_details
        )
        _LOGGER.debug(f"{self.__class__.__name__}: api cache write status: {cache_write_success}")
        return release_details
