from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from plastered.models import AdhocSearch, CacheType, EntityType, LFMRec, RedUserDetails, SearchItem
from plastered.release_search.processors import SearchItemProcessorChain
from plastered.release_search.search_helpers import SearchState
from plastered.run_cache.run_cache import RunCache
from plastered.snatch import Snatcher
from plastered.utils.exceptions import ReleaseSearcherException
from plastered.utils.httpx_utils import LFMAPIClient, MusicBrainzAPIClient, RedAPIClient, RedSnatchAPIClient
from plastered.utils.log_utils import CONSOLE, SPINNER

if TYPE_CHECKING:
    from plastered.config.app_settings import AppSettings, RedSearchOverrides

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

    def search_for_recs(self, entity_to_recs_list: dict[EntityType, list[LFMRec]]) -> None:
        """
        Search for all enabled rec_types scraped from LFM. Then snatch the recs if snatching is enabled.
        """
        search_state, snatcher = self._new_search_state_and_snatcher()
        entity_to_si_list = {
            entity_type: [SearchItem(initial_info=rec) for rec in rec_list]
            for entity_type, rec_list in entity_to_recs_list.items()
        }
        self._apply_si_processor_chain(entity_to_si_list=entity_to_si_list, search_state=search_state)
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
        self, entity_to_si_list: dict[EntityType, list[SearchItem]], search_state: SearchState
    ) -> list[SearchItem]:
        chain = SearchItemProcessorChain(
            lfm=self._lfm_client, mb=self._musicbrainz_client, red=self._red_client, search_state=search_state
        )
        return chain.batch_process(entity_to_si_list=entity_to_si_list)
