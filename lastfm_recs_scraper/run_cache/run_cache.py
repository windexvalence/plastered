from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Callable, Optional

from diskcache import Cache

from lastfm_recs_scraper.config.config_parser import AppConfig
from lastfm_recs_scraper.utils.constants import CACHE_TYPE_API, CACHE_TYPE_SCRAPER
from lastfm_recs_scraper.utils.exceptions import RunCacheException
from lastfm_recs_scraper.utils.logging_utils import get_custom_logger

_LOGGER = get_custom_logger(__name__)


class CacheType(StrEnum):
    """
    Helper enum class used for indicating what type of caching behavior a RunCache instance is meant for.
    """

    API = CACHE_TYPE_API
    SCRAPER = CACHE_TYPE_SCRAPER


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


class RunCache:
    """
    Wrapper class around a diskcache.Cache instance. Used by both
    the LastFMRecsScraper and the ReleaseSearcher by default for caching the data they pull from the web.
    """

    def __init__(self, app_config: AppConfig, cache_type: CacheType):
        self._expiration_datetime = _tomorrow_midnight_datetime()
        self._cache_type = cache_type
        self._enabled = app_config.is_cache_enabled(cache_type=self._cache_type)
        self._cache_dir_path = app_config.get_cache_directory_path(cache_type=self._cache_type)
        self._cache: Optional[Cache] = None
        if self._enabled:
            self._cache = Cache(self._cache_dir_path)
            self._cache.stats(enable=True, reset=True)
            # TODO: make sure that this doesn't need to be called in each load call or more frequently than on construction
            self._cache.expire()
            _LOGGER.info(
                f"Any newly added {self._cache_type.value} cache entries will expire on {self._expiration_datetime.strftime('%Y_%m_%d %H:%M:%S')}"
            )
        self._default_disabled_exception_msg = f"{self._cache_type} cache is not enabled. To enable it, set {self._cache_type.value}_cache_enabled to true in config.yaml."

    @property
    def enabled(self) -> bool:
        return self._enabled

    def print_summary_info(self) -> None:
        if not self._enabled:
            raise RunCacheException(self._default_disabled_exception_msg)
        hits, misses = self._cache.stats()
        print(f"----------------------------------")
        print(f"Cache Summary: {self._cache_type.value}")
        print(f"    Directory path in container: {self._cache_dir_path}")
        print(f"    Disk usage (MB): {self._cache.volume() / float(1e6)}")
        print(f"    Cache hits (prior run):   {hits}")
        print(f"    Cache misses (prior run): {misses}")
        print(f"    Cache hit rate (prior run): {'NA' if hits + misses == 0 else float(hits) / float(hits + misses)}")
        print(f"----------------------------------")

    def clear(self) -> int:
        """
        Clear all entries in the RunCache. Raises a RunCacheException if instance is not enabled.
        """
        if not self._enabled:
            raise RunCacheException(self._default_disabled_exception_msg)
        return self._cache.clear()

    def close(self) -> None:  # pragma: no cover
        """
        Closes the underlying diskcache.Cache instance if the RunCache is enabled, otherwise is a no-op.
        """
        if self._enabled:
            self._cache.close()
            return
        _LOGGER.warning(f"close() call on disabled {self._cache_type} cache has no effect.")

    def load_data_if_valid(self, cache_key: Any, data_validator_fn: Callable) -> Any:
        if not self._enabled:
            _LOGGER.warning(f"{self._cache_type} cache is not enabled.")
            return None
        cached_data = self._cache.get(cache_key)
        if not cached_data:
            return None
        try:
            if not data_validator_fn(cached_data):
                _LOGGER.warning(f"Cached {self._cache_type} data is not valid.")
                return None
        except Exception:
            _LOGGER.error(
                f"Encountered uncaught error during validation of {self._cache_type} data under cache key '{cache_key}'."
            )
            del self._cache[cache_key]
            return None
        return cached_data

    def _seconds_to_expiry(self) -> int:
        return (self._expiration_datetime - datetime.now()).seconds

    def write_data(self, cache_key: Any, data: Any) -> bool:
        if not self._enabled:
            raise RunCacheException(self._default_disabled_exception_msg)
        return self._cache.set(cache_key, data, expire=self._seconds_to_expiry())
