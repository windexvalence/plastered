from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from plastered.db.db_models import FailReason, Status
from plastered.db.db_utils import set_result_status
from plastered.models import AdhocSearch, CacheType, EntityType, LFMRec, RedUserDetails, SearchItem
from plastered.release_search.processors import SearchItemProcessorChain
from plastered.release_search.search_helpers import SearchState
from plastered.run_cache.run_cache import RunCache
from plastered.snatch import Snatcher
from plastered.utils.exceptions import ReleaseSearcherException
from plastered.utils.httpx_utils import LFMAPIClient, MusicBrainzAPIClient, RedAPIClient, RedSnatchAPIClient
from plastered.utils.log_utils import CONSOLE, SPINNER

if TYPE_CHECKING:
    from collections.abc import Callable

    from plastered.config.app_settings import AppSettings, RedSearchOverrides
    from plastered.db.db_models import Matched

_LOGGER = logging.getLogger(__name__)


class ReleaseSearcher:
    """
    General 'brains' for searching for a collection of LFM-recommended releases.
    Responsible for ultimately searching, filtering, and downloading matching releases from RED.
    Optionally may interact with the official LFM API to collect the MBID for a release, and may also optionally
    interact with the official MusicBrainz API to gather more specific search parameters to use on the RED browse endpoint.
    """

    def __init__(
        self,
        app_settings: AppSettings,
        snatch_override: bool | None = None,
        red_user_details: RedUserDetails | None = None,
        red_api_client: RedAPIClient | None = None,
        red_snatch_client: RedSnatchAPIClient | None = None,
        lfm_client: LFMAPIClient | None = None,
        musicbrainz_client: MusicBrainzAPIClient | None = None,
    ):
        # Only own a RunCache when we have to build our own clients; injected clients already carry their own cache.
        clients_provided = all((red_api_client, red_snatch_client, lfm_client, musicbrainz_client))
        self._run_cache = None if clients_provided else RunCache(app_settings=app_settings, cache_type=CacheType.API)
        self._red_client = red_api_client or RedAPIClient(app_settings=app_settings, run_cache=self._run_cache)
        self._red_snatch_client = red_snatch_client or RedSnatchAPIClient(
            app_settings=app_settings, run_cache=self._run_cache
        )
        self._lfm_client = lfm_client or LFMAPIClient(app_settings=app_settings, run_cache=self._run_cache)
        self._musicbrainz_client = musicbrainz_client or MusicBrainzAPIClient(
            app_settings=app_settings, run_cache=self._run_cache
        )
        self._app_settings = app_settings
        self._red_user_details = red_user_details
        self._enable_snatches = (
            snatch_override if snatch_override is not None else app_settings.red.snatches.snatch_recs
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:  # pragma: no cover
            _LOGGER.error(f"ReleaseSearcher encountered an uncaught exception: {exc_val}")
        if self._run_cache:
            self._run_cache.close()
        for client in (self._red_client, self._red_snatch_client, self._lfm_client, self._musicbrainz_client):
            if client:
                client.close_client()

    def search_for_recs(
        self,
        entity_to_recs_list: dict[EntityType, list[LFMRec]],
        snatch_override: bool | None = None,
        progress_callback: Callable[[], None] | None = None,
    ) -> None:
        """
        Search for all enabled rec_types scraped from LFM. Then snatch the recs if snatching is enabled. `snatch_override`
        overrides the configured snatch behavior for this run; `progress_callback` is invoked once per processed rec
        (used by the scraper-run UI to report progress).
        """
        enable_snatches = self._enable_snatches if snatch_override is None else snatch_override
        search_state, snatcher = self._new_search_state_and_snatcher(enable_snatches=enable_snatches)
        entity_to_si_list = {
            entity_type: [SearchItem(initial_info=rec) for rec in rec_list]
            for entity_type, rec_list in entity_to_recs_list.items()
        }
        self._apply_si_processor_chain(
            entity_to_si_list=entity_to_si_list, search_state=search_state, progress_callback=progress_callback
        )
        snatcher.snatch_matches()

    def adhoc_search(
        self, adhoc_search: AdhocSearch, search_id: int, overrides: RedSearchOverrides | None = None
    ) -> None:
        """
        Public entry point for the ad-hoc (manual / on-demand) search flow used by the API. Runs the single provided
        `AdhocSearch` through the processor chain. When snatching is enabled (by config or per-request override) the
        top match is snatched; otherwise the match (if any) is recorded as a `MATCHED` result so it can be returned to
        the client without a download. Not used by the scraper.
        """
        effective_settings = self._app_settings.with_red_overrides(overrides)
        enable_snatches = effective_settings.red.snatches.snatch_recs
        search_state, snatcher = self._new_search_state_and_snatcher(
            app_settings=effective_settings, enable_snatches=enable_snatches
        )
        self._apply_si_processor_chain(
            entity_to_si_list={adhoc_search.entity_type: [SearchItem(initial_info=adhoc_search, search_id=search_id)]},
            search_state=search_state,
        )
        if enable_snatches:
            snatcher.snatch_matches(manual_run=True)
        else:
            search_state.record_matched_result_row()

    def snatch_recorded_match(self, search_id: int, matched: Matched) -> None:
        """
        Snatch a single, already-matched release that was recorded (status `MATCHED`) by a search-only ad-hoc run.

        This backs the per-result "Download" action: the user reviewed the match and chose to download it after the
        fact, so we snatch exactly that torrent (by its recorded tid) without re-running the search. Writes a `GRABBED`
        row on success or a `FAILED` row otherwise. Goes through the shared, throttled `RedSnatchAPIClient`, so the RED
        rate-limit invariant is preserved.
        """
        if matched.tid is None:  # pragma: no cover
            raise ReleaseSearcherException(f"Matched result for search_id={search_id} has no tid to snatch.")
        out_filepath = Path(os.path.join(self._app_settings.red.snatches.snatch_directory, f"{matched.tid}.torrent"))
        exc_name: str | None = None
        _LOGGER.debug(f"Snatching recorded match tid={matched.tid} to {out_filepath} ...")
        try:
            binary_contents = self._red_snatch_client.snatch(tid=str(matched.tid), can_use_token=False)
            out_filepath.write_bytes(binary_contents)
        except Exception as ex:
            if os.path.exists(out_filepath):
                os.remove(out_filepath)
            _LOGGER.error(f"Failed to snatch recorded match tid={matched.tid}: ", exc_info=True)
            exc_name = ex.__class__.__name__
        if exc_name is not None:
            fail_reason = (
                FailReason(exc_name)
                if exc_name in (FailReason.RED_API_REQUEST_ERROR, FailReason.FILE_ERROR)
                else FailReason.OTHER
            )
            set_result_status(
                search_id=search_id,
                status=Status.FAILED,
                status_model_kwargs={
                    "red_permalink": matched.red_permalink,
                    "matched_mbid": matched.matched_mbid,
                    "fail_reason": fail_reason,
                },
            )
            return
        fl_token_used = self._red_snatch_client.tid_snatched_with_fl_token(tid=matched.tid)
        set_result_status(
            search_id=search_id,
            status=Status.GRABBED,
            status_model_kwargs={"fl_token_used": fl_token_used, "snatch_path": str(out_filepath), "tid": matched.tid},
        )

    def _new_search_state_and_snatcher(
        self, app_settings: AppSettings | None = None, enable_snatches: bool | None = None
    ) -> tuple[SearchState, Snatcher]:
        """
        Builds the fresh, per-run mutable `SearchState` (and its `Snatcher`) for a single search invocation. Keeping
        this state out of `__init__` lets a single `ReleaseSearcher` be reused across calls (e.g. the FastAPI app
        builds it once at startup) without one run's matches leaking into the next. The ad-hoc flow passes effective
        (override-merged) settings and an explicit snatch toggle; the scraper flow uses the searcher's own defaults.
        """
        app_settings = app_settings if app_settings is not None else self._app_settings
        enable_snatches = self._enable_snatches if enable_snatches is None else enable_snatches
        search_state = SearchState(app_settings=app_settings, red_user_details=self._red_user_details)
        if not search_state.red_user_details_is_initialized():
            self._gather_red_user_details(search_state=search_state)
        snatcher = Snatcher(
            red_snatch_client=self._red_snatch_client,
            search_state=search_state,
            snatch_directory=app_settings.red.snatches.snatch_directory,
            enable_snatches=enable_snatches,
        )
        return search_state, snatcher

    def _gather_red_user_details(self, search_state: SearchState) -> None:
        if self._red_snatch_client is None:  # pragma: no cover
            raise ReleaseSearcherException("red snatch client is not initialized.")
        if search_state.red_user_details_is_initialized():  # pragma: no cover
            _LOGGER.info("RedUserDetails instance already initialized.")
        else:
            if self._red_client is None:  # pragma: no cover
                raise ReleaseSearcherException("red client is not initialized.")
            with CONSOLE.status(
                "Gathering RED user details to calculate ratio limits and to filter out prior snatches ...",
                spinner=SPINNER,
            ):
                red_user_details = self._red_client.get_red_user_details()
            # Cache the details on the instance so a reused ReleaseSearcher only fetches them once.
            self._red_user_details = red_user_details
            search_state.set_red_user_details(red_user_details=red_user_details)

    def _apply_si_processor_chain(
        self,
        entity_to_si_list: dict[EntityType, list[SearchItem]],
        search_state: SearchState,
        progress_callback: Callable[[], None] | None = None,
    ) -> list[SearchItem]:
        chain = SearchItemProcessorChain(
            lfm=self._lfm_client, mb=self._musicbrainz_client, red=self._red_client, search_state=search_state
        )
        return chain.batch_process(entity_to_si_list=entity_to_si_list, progress_callback=progress_callback)
