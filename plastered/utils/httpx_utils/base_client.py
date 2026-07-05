import logging
import threading
from datetime import datetime, timedelta
from time import perf_counter_ns
from typing import Final

import httpx
from tenacity import Retrying, stop_after_attempt, wait_fixed

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
        extra_client_transport_mount_entries: dict[str, httpx.BaseTransport] | None = None,
    ):
        self._max_api_call_retries = max_api_call_retries
        self._throttle_period = timedelta(seconds=seconds_between_api_calls)
        self._extra_client_transport_mount_entries = extra_client_transport_mount_entries or {}

        # initialize _time_of_last_call to midnight of the current day
        init_time = datetime.now()
        self._time_of_last_call = datetime(
            year=init_time.year, month=init_time.month, day=init_time.day, hour=0, minute=0
        )
        # Serializes the throttle across threads so background-task threads can't race the rate limiter and exceed it.
        # With the server run single-process (server.workers = 1), this makes the per-API rate limit process-global.
        self._throttle_lock = threading.Lock()
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
        Helper method which the subclasses will call prior to submitting an API request. Ensures we are throttling each
        client request. The wait + timestamp update are guarded by a lock so concurrent caller threads (FastAPI runs
        sync endpoints/background tasks in an anyio worker-thread pool) are serialized and can't collectively exceed the
        configured rate. Callers must run off the event loop (e.g. via run_in_threadpool / a background task) so the
        busy-wait — and this lock — never block the loop.
        """
        with self._throttle_lock:
            time_since_last_call = datetime.now() - self._time_of_last_call
            if time_since_last_call < self._throttle_period:
                wait_seconds = (self._throttle_period - time_since_last_call).seconds
                precise_delay(sec_delay=wait_seconds)
            self._time_of_last_call = datetime.now()
