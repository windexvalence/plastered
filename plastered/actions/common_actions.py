import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session

from plastered.config.app_settings import AppSettings
from plastered.db.db_models import ScraperRunStatus
from plastered.db.db_utils import create_scraper_run, update_scraper_run
from plastered.models import CacheType, EntityType
from plastered.release_search.release_searcher import ReleaseSearcher
from plastered.run_cache.run_cache import RunCache
from plastered.scraper.lfm_scraper import LFMRecsScraper
from plastered.utils.constants import CLI_ALL_CACHE_TYPES
from plastered.utils.exceptions import RunCacheDisabledException

_LOGGER = logging.getLogger(__name__)


def _now_ts() -> int:
    return int(datetime.now(tz=UTC).timestamp())


def run_lfm_scraper(
    app_settings: AppSettings,
    release_searcher: ReleaseSearcher,
    run_id: int,
    rec_types_to_scrape_override: list[EntityType] | None,
    snatch_enabled: bool,
) -> None:
    """
    Core LFM-recommendations scraper run for the `ScraperRun` identified by `run_id`: scrape the recommendation pages,
    then search/snatch each rec, updating the run's live progress (stage + processed/total recs) as it goes. Marks the
    run COMPLETED on success or FAILED (with the error) on any exception.
    """
    try:
        update_scraper_run(run_id=run_id, stage="scraping")
        with LFMRecsScraper(
            app_settings=app_settings, rec_types_to_scrape_override=rec_types_to_scrape_override
        ) as scraper:
            entity_to_recs_list = scraper.scrape_recs()
        total_recs = sum(len(recs) for recs in entity_to_recs_list.values())
        update_scraper_run(
            run_id=run_id, stage="searching", progress_current=0, progress_total=total_recs, total_recs=total_recs
        )

        processed_count = {"n": 0}

        def _on_rec_processed() -> None:
            processed_count["n"] += 1
            update_scraper_run(run_id=run_id, progress_current=processed_count["n"])

        release_searcher.search_for_recs(
            entity_to_recs_list=entity_to_recs_list, snatch_override=snatch_enabled, progress_callback=_on_rec_processed
        )
        update_scraper_run(run_id=run_id, status=ScraperRunStatus.COMPLETED, stage="done", finished_timestamp=_now_ts())
    except Exception as ex:
        _LOGGER.error(f"LFM scraper run {run_id} failed: ", exc_info=True)
        update_scraper_run(run_id=run_id, status=ScraperRunStatus.FAILED, error=str(ex), finished_timestamp=_now_ts())
        raise


def scrape_action(
    app_settings: AppSettings,
    rec_types_to_scrape_override: list[EntityType] | None = None,
    snatch_override: bool | None = None,
    session: Session | None = None,
) -> None:
    """Entrypoint for a (synchronous) scrape run. Records a `ScraperRun` so the run shows up in the history UI."""
    snatch_enabled = snatch_override if snatch_override is not None else app_settings.red.snatches.snatch_recs
    effective_rec_types = (
        [rec_type.value for rec_type in rec_types_to_scrape_override]
        if rec_types_to_scrape_override
        else app_settings.lfm.rec_types_to_scrape
    )
    run_id = create_scraper_run(
        snatch_enabled=snatch_enabled, rec_types=effective_rec_types, submit_timestamp=_now_ts()
    )
    run_lfm_scraper(
        app_settings=app_settings,
        release_searcher=ReleaseSearcher(app_settings=app_settings, snatch_override=snatch_override),
        run_id=run_id,
        rec_types_to_scrape_override=rec_types_to_scrape_override,
        snatch_enabled=snatch_enabled,
    )


def show_config_action(app_settings: AppSettings) -> dict[str, Any]:
    """Wrapper function for entrypoint of read-only config actions."""
    return json.loads(app_settings.model_dump_json())


def cache_action(
    app_settings: AppSettings,
    target_cache: str,
    empty: bool | None = False,
    check: bool | None = False,
    list_keys: bool | None = False,
    read_value: str | None = None,
) -> None:
    """Wrapper function for entrypoint of cache-related actions."""
    if target_cache == CLI_ALL_CACHE_TYPES:
        target_cache_types = [cache_type for cache_type in CacheType]
    else:
        target_cache_types = [CacheType(target_cache)]
    for target_cache_type in target_cache_types:
        target_run_cache = RunCache(app_settings=app_settings, cache_type=target_cache_type)
        try:
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
