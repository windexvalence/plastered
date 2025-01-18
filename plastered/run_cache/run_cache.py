import logging
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Callable, List, Optional

from diskcache import Cache

from plastered.config.config_parser import AppConfig
from plastered.stats.stats import RunCacheSummaryTable
from plastered.utils.constants import CACHE_TYPE_API, CACHE_TYPE_SCRAPER
from plastered.utils.exceptions import RunCacheDisabledException

_LOGGER = logging.getLogger(__name__)


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
    the LFMRecsScraper and the ReleaseSearcher by default for caching the data they pull from the web.
    """

    def __init__(self, app_config: AppConfig, cache_type: CacheType):
        self._expiration_datetime = _tomorrow_midnight_datetime()
        self._cache_type = cache_type
        self._enabled = app_config.is_cache_enabled(cache_type=self._cache_type)
        _LOGGER.debug(f"This is a debug message")
        _LOGGER.info(f"RunCache of type {self._cache_type.value} instantiated and enabled set to: {self._enabled}")
        self._cache_dir_path = app_config.get_cache_directory_path(cache_type=self._cache_type)
        _LOGGER.info(f"RunCache of type {self._cache_type.value} directory path: {self._cache_dir_path}")
        self._cache: Optional[Cache] = None
        if self._enabled:
            _LOGGER.info(f"Enabling diskcache for {self._cache_type.value} ...")
            self._cache = Cache(self._cache_dir_path)
            _LOGGER.info(f"diskcache instantiated for {self._cache_type.value} ...")
            self._cache.stats(enable=True, reset=True)
            # TODO: make sure that this doesn't need to be called in each load call or more frequently than on construction
            num_expired = self._cache.expire()
            _LOGGER.info(f"{num_expired} expired entries detected in {self._cache_type.value} cache.")
            _LOGGER.info(
                f"Any newly added {self._cache_type.value} cache entries will expire on {self._expiration_datetime.strftime('%Y_%m_%d %H:%M:%S')}"
            )
        self._default_disabled_exception_msg = f"{self._cache_type} cache is not enabled. To enable it, set {self._cache_type.value}_cache_enabled to true in config.yaml."

    @property
    def enabled(self) -> bool:
        return self._enabled

    def print_summary_info(self) -> None:
        if not self._enabled:
            raise RunCacheDisabledException(self._default_disabled_exception_msg)
        disk_usage_mb = self._cache.volume() / float(1e6)
        hits, misses = self._cache.stats()
        hit_rate_str = "NA" if hits + misses == 0 else str(float(hits) / float(hits + misses))
        RunCacheSummaryTable(
            cache_type_str=self._cache_type.value,
            disk_usage_mb=str(disk_usage_mb),
            hits=str(hits),
            misses=str(misses),
            hit_rate=hit_rate_str,
            directory_path=self._cache_dir_path,
        ).print_table()
        # print(f"----------------------------------")
        # print(f"Cache Summary: {self._cache_type.value}")
        # print(f"    Directory path in container: {self._cache_dir_path}")
        # print(f"    Disk usage (MB): {}")
        # print(f"    Cache hits (prior run):   {hits}")
        # print(f"    Cache misses (prior run): {misses}")
        # print(f"    Cache hit rate (prior run): {}")
        # if self._cache_type == CacheType.API:
        #     base_domain_cache_cnts = defaultdict(int)
        #     for cache_key in self._cache.iterkeys():
        #         base_domain_cache_cnts[cache_key[0]] += 1
        #     print(f"    Cache entries by base domains: {list(base_domain_cache_cnts.items())}")
        # print(f"----------------------------------")

    def clear(self) -> None:
        """
        Clear all entries in the RunCache. Raises a RunCacheDisabledException if instance is not enabled.
        """
        if not self._enabled:
            raise RunCacheDisabledException(self._default_disabled_exception_msg)
        num_entries_removed = self._cache.clear()
        _LOGGER.info(f"{self._cache_type.value} emptied: {num_entries_removed} entries removed.")

    def close(self) -> None:  # pragma: no cover
        """
        Closes the underlying diskcache.Cache instance if the RunCache is enabled, otherwise is a no-op.
        """
        if self._enabled:
            self._cache.close()
            return
        _LOGGER.warning(f"close() call on disabled {self._cache_type} cache has no effect.")

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
            _LOGGER.warning(f"{self._cache_type.value} diskcache warnings: ")
            _LOGGER.warning("\n".join(diskcache_warnings))

    def load_data_if_valid(self, cache_key: Any, data_validator_fn: Callable) -> Any:
        if not self._enabled:
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
            raise RunCacheDisabledException(self._default_disabled_exception_msg)
        return self._cache.set(cache_key, data, expire=self._seconds_to_expiry())
