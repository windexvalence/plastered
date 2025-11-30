import logging
from datetime import datetime, timedelta
from time import perf_counter_ns
from typing import Any, Final

import httpx
from tenacity import Retrying, stop_after_attempt, wait_fixed

from plastered.run_cache.run_cache import RunCache

LOGGER = logging.getLogger(__name__)
_NANOSEC_TO_SEC: Final[float] = 1e9


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

    def __init__(self, max_retries: int, min_wait_seconds: int):
        self._max_retries = max_retries
        self._min_wait_seconds = min_wait_seconds
        self._transport = httpx.HTTPTransport()

    # NOTE: non-decorated tenacity retry logic which resets per-call to handle_request was adopted
    # from this SO answer: https://stackoverflow.com/a/62238110
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        for attempt in Retrying(
            wait=wait_fixed(self._min_wait_seconds), stop=stop_after_attempt(self._max_retries), reraise=True
        ):
            with attempt:
                LOGGER.debug(f"Handling request attempt number: {attempt.retry_state.attempt_number} ...")
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
        valid_endpoints: set[str],
        run_cache: RunCache | None = None,
        non_cached_endpoints: set[str] | None = None,
        extra_client_transport_mount_entries: dict[str, httpx.BaseTransport] | None = None,
    ):
        self._max_api_call_retries = max_api_call_retries
        self._throttle_period = timedelta(seconds=seconds_between_api_calls)
        self._valid_endpoints = valid_endpoints
        if run_cache is None:
            LOGGER.warning(
                f"{self.__class__.__name__}: No run cache instance provided. Caching disabled for this client."
            )
        self._run_cache = run_cache
        self._non_cached_endpoints: set[str] = non_cached_endpoints or set()
        self._extra_client_transport_mount_entries = extra_client_transport_mount_entries or {}

        # initialize _time_of_last_call to midnight of the current day
        init_time = datetime.now()
        self._time_of_last_call = datetime(
            year=init_time.year, month=init_time.month, day=init_time.day, hour=0, minute=0
        )
        self._base_domain = base_api_url
        self._client = httpx.Client(
            mounts={
                self._base_domain: HTTPXRetryTransport(
                    max_retries=self._max_api_call_retries, min_wait_seconds=self._throttle_period.seconds
                )
            }
            | self._extra_client_transport_mount_entries,  # type: ignore
            follow_redirects=True,
        )

    # Too much of a pain in the ass to write a test for
    def close_client(self) -> None:  # pragma: no cover
        if self._client:
            self._client.close()

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

    def _construct_cache_key(self, endpoint: str, params: str) -> tuple[str, str, str]:
        """
        The universal cache key construction across all the ThrottleAPIClient subclasses. This simplifies
        the code while allowing each subclass instance to share the same cache instance without collisions due to
        their cache keys being distinguished by the self._base_domain key prefix.
        """
        return (self._base_domain, endpoint, params)

    def _read_from_run_cache(self, endpoint: str, params: str) -> dict[str, Any] | None:
        """
        Return the cached API response if one exists and is valid, otherwise return None.
        Raises a ValueError if the provided endpoint is not in self._valid_endpoints.
        """
        if endpoint not in self._valid_endpoints:
            raise ValueError(
                f"Invalid endpoint provided to {self.__class__.__name__}: '{endpoint}'. Valid endpoints are: {self._valid_endpoints}"
            )
        if endpoint in self._non_cached_endpoints:
            LOGGER.debug(
                f"{self.__class__.__name__}: Skipping read from api cache. endpoint '{endpoint}' is categorized as non-cacheable: {endpoint in self._non_cached_endpoints}"
            )
            return None
        if self._run_cache is None:
            LOGGER.debug(f"{self.__class__.__name__}: No run cache initialized for this client instance.")
            return None
        return self._run_cache.load_data_if_valid(
            cache_key=self._construct_cache_key(endpoint=endpoint, params=params),
            data_validator_fn=lambda x: isinstance(x, dict),
        )

    def _write_cache_if_enabled(self, endpoint: str, params: str, result_json: dict[str, Any]) -> bool:
        if self._run_cache is None:
            LOGGER.debug(
                f"{self.__class__.__name__}: Skip cache write. No run cache initialized for this client instance."
            )
            return False
        if endpoint in self._non_cached_endpoints or not self._run_cache.enabled:
            LOGGER.debug(
                f"{self.__class__.__name__}: Skipping write to api cache. Endpoint '{endpoint}' non-cacheable: {endpoint in self._non_cached_endpoints}"
            )
            return False
        return self._run_cache.write_data(
            cache_key=self._construct_cache_key(endpoint=endpoint, params=params), data=result_json
        )
