import json
import logging
import sys
from typing import Any

from sqlmodel import Session

from plastered.config.app_settings import AppSettings
from plastered.release_search.release_searcher import ReleaseSearcher
from plastered.run_cache.run_cache import CacheType, RunCache
from plastered.scraper.lfm_scraper import LFMRecsScraper
from plastered.utils.constants import API_ALL_CACHE_TYPES, CLI_ALL_CACHE_TYPES
from plastered.utils.exceptions import RunCacheDisabledException

_LOGGER = logging.getLogger(__name__)


def scrape_action(app_settings: AppSettings, session: Session | None = None) -> None:
    """Wrapper function for entrypoint of scrape actions."""
    with LFMRecsScraper(app_settings=app_settings) as scraper:
        rec_types_to_recs_list = scraper.scrape_recs()
    with ReleaseSearcher(app_settings=app_settings) as release_searcher:
        release_searcher.search_for_recs(rec_type_to_recs_list=rec_types_to_recs_list)


def show_config_action(app_settings: AppSettings) -> dict[str, Any]:
    """Wrapper function for entrypoint of read-only config actions."""
    return json.loads(app_settings.model_dump_json())


def cache_action(
    app_settings: AppSettings,
    target_cache: str,
    info: bool | None = False,
    empty: bool | None = False,
    check: bool | None = False,
    list_keys: bool | None = False,
    read_value: str | None = None,
) -> None:
    """Wrapper function for entrypoint of cache-related actions."""
    if target_cache in (API_ALL_CACHE_TYPES, CLI_ALL_CACHE_TYPES):
        target_cache_types = [cache_type for cache_type in CacheType]
    else:
        target_cache_types = [CacheType(target_cache)]
    for target_cache_type in target_cache_types:
        target_run_cache = RunCache(app_settings=app_settings, cache_type=target_cache_type)
        try:
            if info:
                target_run_cache.print_summary_info()
            if empty:
                target_run_cache.clear()
            if check:
                target_run_cache.check()
            if list_keys:
                target_run_cache.cli_list_cache_keys()
            if read_value:
                target_run_cache.cli_print_cached_value(key=read_value)
        except RunCacheDisabledException:
            _LOGGER.error(
                f"{target_cache_type} cache is not enabled. To enable it, set enable_{target_cache_type}_cache to true in config.yaml."
            )
            sys.exit(2)
        target_run_cache.close()
