import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from diskcache import Cache

from plastered.config.app_settings import AppSettings
from plastered.utils.exceptions import RunCacheDisabledException

LOGGER = logging.getLogger(__name__)


def _tomorrow_midnight_datetime() -> datetime:
    """
    Helper function for calculating the default cache expiration datetime.
    If this is invoked within 20 minutes before midnight, it will return
    the following midnight datetime to give some additional leeway.
    """
    now_dt = datetime.now()
    days_increment = 1
    # If this is run 20 minutes or less before midnight, return the following midnight datetime to add some leeway
    if now_dt.hour == 23 and now_dt.minute >= 40:
        days_increment = 2
    return datetime.combine(now_dt.date() + timedelta(days=days_increment), datetime.min.time())


# TODO (later) define __enter__ and __exit__ methods for cleaner shutdown, and invoke the ctx mgr from the LFMRecsScraper.
class RunCache:
    """
    Wrapper class around a diskcache.Cache instance. Used by the LFMRecsScraper to cache the recommendations it
    scrapes from Last.fm. (The API clients no longer cache their responses.)
    """

    def __init__(self, app_settings: AppSettings, cache_type: str):
        self._expiration_datetime = _tomorrow_midnight_datetime()
        self._cache_type = cache_type
        self._enabled = app_settings.is_cache_enabled(cache_type=self._cache_type)
        LOGGER.debug(f"RunCache of type {self._cache_type} instantiated and enabled set to: {self._enabled}")
        self._cache_dir_path = app_settings.get_cache_directory_path(cache_type=self._cache_type)
        LOGGER.debug(f"RunCache of type {self._cache_type} directory path: {self._cache_dir_path}")
        if self._enabled:
            LOGGER.debug(f"Enabling diskcache for {self._cache_type} ...")
            self._cache = Cache(self._cache_dir_path)
            LOGGER.debug(f"diskcache instantiated for {self._cache_type} ...")
            self._cache.stats(enable=True, reset=True)
            # TODO: make sure that this doesn't need to be called in each load call or more frequently than on construction
            num_expired = self._cache.expire()
            LOGGER.debug(f"{num_expired} expired entries detected in {self._cache_type} cache.")
            LOGGER.info(
                f"Any newly added {self._cache_type} cache entries will expire on {self._expiration_datetime.strftime('%Y_%m_%d %H:%M:%S')}"
            )
        self._default_disabled_exception_msg = f"{self._cache_type} cache is not enabled. To enable it, set {self._cache_type}_cache_enabled to true in config.yaml."

    @property
    def enabled(self) -> bool:
        return self._enabled

    def close(self) -> None:  # pragma: no cover
        """
        Closes the underlying diskcache.Cache instance if the RunCache is enabled, otherwise is a no-op.
        """
        if self._enabled:
            self._cache.close()
            return
        LOGGER.warning(f"close() call on disabled {self._cache_type} cache has no effect.")

    def load_data_if_valid(self, cache_key: Any, data_validator_fn: Callable) -> Any:
        if not self._enabled:
            return None
        cached_data = self._cache.get(cache_key)
        if not cached_data:
            return None
        try:
            if not data_validator_fn(cached_data):
                LOGGER.warning(f"Cached {self._cache_type} data is not valid.")
                return None
        except Exception:
            LOGGER.error(
                f"Encountered uncaught error during validation of {self._cache_type} data under cache key '{cache_key}'."
            )
            del self._cache[cache_key]
            return None
        return cached_data

    def _seconds_to_expiry(self) -> int:
        return (self._expiration_datetime - datetime.now()).seconds

    def write_data(self, cache_key: Any, data: Any) -> bool:
        if not self._enabled:
            raise RunCacheDisabledException(self._default_disabled_exception_msg)
        return self._cache.set(cache_key, data, expire=self._seconds_to_expiry())
