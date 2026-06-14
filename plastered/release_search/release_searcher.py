from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from plastered.db.db_utils import get_result_by_id
from plastered.models import CacheType, EntityType, LFMRec, ManualSearch, RedUserDetails, SearchItem
from plastered.release_search.processors import SearchItemProcessorChain
from plastered.release_search.search_helpers import SearchState
from plastered.run_cache.run_cache import RunCache
from plastered.utils.exceptions import ReleaseSearcherException
from plastered.utils.httpx_utils import LFMAPIClient, MusicBrainzAPIClient, RedAPIClient, RedSnatchAPIClient
from plastered.utils.log_utils import CONSOLE, SPINNER

if TYPE_CHECKING:
    from plastered.config.app_settings import AppSettings

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
        self._run_cache = RunCache(app_settings=app_settings, cache_type=CacheType.API)
        self._red_client = red_api_client or RedAPIClient(app_settings=app_settings, run_cache=self._run_cache)
        self._red_snatch_client = red_snatch_client or RedSnatchAPIClient(
            app_settings=app_settings, run_cache=self._run_cache
        )
        self._lfm_client = lfm_client or LFMAPIClient(app_settings=app_settings, run_cache=self._run_cache)
        self._musicbrainz_client = musicbrainz_client or MusicBrainzAPIClient(
            app_settings=app_settings, run_cache=self._run_cache
        )
        self._red_user_id = app_settings.red.red_user_id
        self._search_state = SearchState(app_settings=app_settings, red_user_details=red_user_details)
        self._enable_snatches = (
            snatch_override if snatch_override is not None else app_settings.red.snatches.snatch_recs
        )
        self._snatch_directory = app_settings.red.snatches.snatch_directory

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:  # pragma: no cover
            _LOGGER.error(f"ReleaseSearcher encountered an uncaught exception: {exc_val}")
        self._run_cache.close()
        if self._red_client:
            self._red_client.close_client()
        if self._red_snatch_client:
            self._red_snatch_client.close_client()
        if self._lfm_client:
            self._lfm_client.close_client()
        if self._musicbrainz_client:
            self._musicbrainz_client.close_client()

    def search_for_recs(self, entity_to_recs_list: dict[EntityType, list[LFMRec]]) -> None:
        """
        Search for all enabled rec_types scraped from LFM. Then snatch the recs if snatching is enabled.
        """
        if not self._search_state.red_user_details_is_initialized():
            self._gather_red_user_details()
        entity_to_si_list = {
            entity_type: [SearchItem(initial_info=rec) for rec in rec_list]
            for entity_type, rec_list in entity_to_recs_list.items()
        }
        self._apply_si_processor_chain(entity_to_si_list=entity_to_si_list)
        self._snatch_matches()

    def manual_search(self, search_id: int, mbid: str | None = None) -> None:
        """Public method that the manual search endpoint should invoke. Not used by the scraper."""
        if not self._search_state.red_user_details_is_initialized():
            self._gather_red_user_details()

        manual_search_instance = ManualSearch.from_search_record(get_result_by_id(search_id=search_id), mbid)
        self._apply_si_processor_chain(
            entity_to_si_list={
                manual_search_instance.entity_type: [
                    SearchItem(initial_info=manual_search_instance, search_id=search_id)
                ]
            }
        )
        self._snatch_matches(manual_run=True)

    # TODO (later): make this method call happen exclusively within the __enter__ method
    def _gather_red_user_details(self) -> None:
        if self._red_snatch_client is None:  # pragma: no cover
            raise ReleaseSearcherException("red snatch client is not initialized.")
        if self._search_state.red_user_details_is_initialized():  # pragma: no cover
            _LOGGER.info("RedUserDetails instance already initialized.")
        else:
            if self._red_client is None:  # pragma: no cover
                raise ReleaseSearcherException("red client is not initialized.")
            with CONSOLE.status(
                "Gathering RED user details to calculate ratio limits and to filter out prior snatches ...",
                spinner=SPINNER,
            ):
                red_user_details = self._red_client.get_red_user_details()
            self._search_state.set_red_user_details(red_user_details=red_user_details)

    def _apply_si_processor_chain(self, entity_to_si_list: dict[EntityType, list[SearchItem]]) -> list[SearchItem]:
        chain = SearchItemProcessorChain(
            lfm=self._lfm_client, mb=self._musicbrainz_client, red=self._red_client, search_state=self._search_state
        )
        return chain.batch_process(entity_to_si_list=entity_to_si_list)

    # TODO: create separate class and db model for snatches
    def _snatch_matches(self, manual_run: bool = False) -> None:
        if not self._enable_snatches:
            _LOGGER.warning("Not configured to snatch. Please update your config to enable.")
            return
        if search_items_to_snatch := self._search_state.get_search_items_to_snatch(manual_run=manual_run):
            _LOGGER.debug(f"Beginning to snatch matched torrents to download directory '{self._snatch_directory}' ...")
            for si_to_snatch in search_items_to_snatch:
                self._snatch_match(si_to_snatch=si_to_snatch)
        else:  # pragma: no cover
            _LOGGER.warning("No torrents matched to your LFM recs. Consider adjusting the search config preferences.")

    # TODO: create separate class and db model for snatches
    def _snatch_match(self, si_to_snatch: SearchItem) -> None:
        te_to_snatch = si_to_snatch.torrent_entry
        if not te_to_snatch:  # pragma: no cover
            _LOGGER.error("SearchItem marked for snatching unexpected missing torrent entry: ")
            return
        tid = te_to_snatch.torrent_id
        permalink = te_to_snatch.get_permalink_url()
        out_filepath = Path(os.path.join(self._snatch_directory, f"{tid}.torrent"))
        exc_name: str | None = None
        _LOGGER.debug(f"Snatching {permalink} and saving to {out_filepath} ...")
        try:
            binary_contents = self._red_snatch_client.snatch(tid=str(tid), can_use_token=te_to_snatch.can_use_token)
            out_filepath.write_bytes(binary_contents)
        except Exception as ex:  # pragma: no cover
            # Delete any potential file artifacts in case the failure took place in the middle of the .torrent file writing.
            if os.path.exists(out_filepath):
                os.remove(out_filepath)
            _LOGGER.error(f"Failed to snatch due to uncaught error for: {permalink}: ", exc_info=True)
            exc_name = ex.__class__.__name__
        finally:
            fl_token_used = self._red_snatch_client.tid_snatched_with_fl_token(tid=tid)
            self._search_state.add_snatch_final_status_row(
                si=si_to_snatch, snatched_with_fl=fl_token_used, snatch_path=str(out_filepath), exc_name=exc_name
            )
