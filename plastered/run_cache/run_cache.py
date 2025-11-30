import json
import logging
from ast import literal_eval as make_tuple
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from diskcache import Cache

from plastered.config.app_settings import AppSettings
from plastered.models.types import CacheType
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


# TODO (later) define __enter__ and __exit__ methods for cleaner shutdown, and invoke the ctx mgr from calling ReleaseSearcher / API ctx mgrs.
class RunCache:
    """
    Wrapper class around a diskcache.Cache instance. Used by both
    the LFMRecsScraper and the ReleaseSearcher by default for caching the data they pull from the web.
    """

    def __init__(self, app_settings: AppSettings, cache_type: CacheType):
        self._expiration_datetime = _tomorrow_midnight_datetime()
        self._cache_type = cache_type
        self._enabled = app_settings.is_cache_enabled(cache_type=self._cache_type)
        LOGGER.debug(f"RunCache of type {self._cache_type.value} instantiated and enabled set to: {self._enabled}")
        self._cache_dir_path = app_settings.get_cache_directory_path(cache_type=self._cache_type)
        LOGGER.debug(f"RunCache of type {self._cache_type.value} directory path: {self._cache_dir_path}")
        # self._cache: Cache | None = None
        if self._enabled:
            LOGGER.debug(f"Enabling diskcache for {self._cache_type.value} ...")
            self._cache = Cache(self._cache_dir_path)
            LOGGER.debug(f"diskcache instantiated for {self._cache_type.value} ...")
            self._cache.stats(enable=True, reset=True)
            # TODO: make sure that this doesn't need to be called in each load call or more frequently than on construction
            num_expired = self._cache.expire()
            LOGGER.debug(f"{num_expired} expired entries detected in {self._cache_type.value} cache.")
            LOGGER.info(
                f"Any newly added {self._cache_type.value} cache entries will expire on {self._expiration_datetime.strftime('%Y_%m_%d %H:%M:%S')}"
            )
        self._default_disabled_exception_msg = f"{self._cache_type} cache is not enabled. To enable it, set {self._cache_type.value}_cache_enabled to true in config.yaml."

    @property
    def enabled(self) -> bool:
        return self._enabled

    def clear(self) -> None:
        """
        Clear all entries in the RunCache. Raises a RunCacheDisabledException if instance is not enabled.
        """
        if not self._enabled:
            raise RunCacheDisabledException(self._default_disabled_exception_msg)
        num_entries_removed = self._cache.clear()
        LOGGER.info(f"{self._cache_type.value} emptied: {num_entries_removed} entries removed.")

    def close(self) -> None:  # pragma: no cover
        """
        Closes the underlying diskcache.Cache instance if the RunCache is enabled, otherwise is a no-op.
        """
        if self._enabled:
            self._cache.close()
            return
        LOGGER.warning(f"close() call on disabled {self._cache_type} cache has no effect.")

    def check(self) -> None:
        """
        Runs disckcache.Cache's check() method if enabled.
        diskcache.Cache's check() call verifies cache consistency.
        It can also fix inconsistencies and reclaim unused space. Logs any discovered warnings.
        """
        if not self._enabled:
            raise RunCacheDisabledException(self._default_disabled_exception_msg)
        diskcache_warnings = self._cache.check()
        if diskcache_warnings:
            LOGGER.warning(f"{self._cache_type.value} diskcache warnings: ")
            LOGGER.warning("\n".join(diskcache_warnings))

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

    def cli_list_cache_keys(self) -> None:
        """
        Convenience method exclusively for use by the cache CLI command.
        Prints the list of string representations of all currently available cache keys.
        """
        if not self._enabled:
            raise RunCacheDisabledException(self._default_disabled_exception_msg)
        for str_key in [str(raw_key) for raw_key in list(self._cache)]:
            print(str_key)

    def cli_print_cached_value(self, key: str) -> None:
        """
        Convenience method exclusively for use by the cache CLI command.
        Prints the string representation of the cached value assigned to the given cache key.
        """
        if not self._enabled:
            raise RunCacheDisabledException(self._default_disabled_exception_msg)
        if self._cache_type == CacheType.API:
            key = make_tuple(key)
        value = self._cache.get(key)
        if self._cache_type == CacheType.API:
            print(json.dumps(str(value)))
            return
        print("[")
        for rec in value:
            print(f"\t{str(rec)},")
        print("]")
