import logging
import os

from plastered.config.app_settings import AppSettings
from plastered.db.db_utils import get_result_by_id
from plastered.models.lfm_models import LFMAlbumInfo, LFMRec, LFMTrackInfo
from plastered.models.manual_search_models import ManualSearch
from plastered.models.musicbrainz_models import MBRelease
from plastered.models.red_models import RedUserDetails, ReleaseEntry, TorrentMatch
from plastered.models.search_item import SearchItem
from plastered.models.types import CacheType, EntityType
from plastered.release_search.search_helpers import SearchState
from plastered.run_cache.run_cache import RunCache
from plastered.utils.exceptions import LFMClientException, MusicBrainzClientException, ReleaseSearcherException
from plastered.utils.httpx_utils.lfm_client import LFMAPIClient
from plastered.utils.httpx_utils.musicbrainz_client import MusicBrainzAPIClient
from plastered.utils.httpx_utils.red_client import RedAPIClient
from plastered.utils.httpx_utils.red_snatch_client import RedSnatchAPIClient
from plastered.utils.log_utils import CONSOLE, SPINNER, NestedProgress, red_browse_progress

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
                red_user_details = self._red_client.create_red_user_details()
            self._search_state.set_red_user_details(red_user_details=red_user_details)

    def _search_red_release_by_preferences(self, si: SearchItem, rich_progress: NestedProgress) -> TorrentMatch:
        above_max_size_found = False
        with red_browse_progress(release_name=si.release_name, artist_name=si.artist_name, parent_prog=rich_progress):
            for pref in self._search_state.red_format_preferences:
                _LOGGER.debug(f"Searching Artist: '{si.artist_name}', release: '{si.release_name}', {pref=}")
                browse_request_params = self._search_state.create_red_browse_params(red_format=pref, si=si)
                try:
                    red_browse_response = self._red_client.request_api(action="browse", params=browse_request_params)
                except Exception:
                    _LOGGER.error(
                        f"Uncaught exception during RED browse request: {browse_request_params}: ", exc_info=True
                    )
                    continue
                release_entries_browse_response = [
                    ReleaseEntry.from_torrent_search_json_blob(json_blob=result_blob)
                    for result_blob in red_browse_response["results"]
                ]

                # Find best entry from the RED browse response
                for release_entry in release_entries_browse_response:
                    for torrent_entry in release_entry.get_torrent_entries():
                        _LOGGER.debug(f"Checking size of torrent entry: {torrent_entry}")
                        size_gb = torrent_entry.get_size(unit="GB")
                        if size_gb <= self._search_state.max_size_gb:
                            _LOGGER.debug(f"Torrent match found. ID: {torrent_entry.torrent_id}")
                            return TorrentMatch(torrent_entry=torrent_entry, above_max_size_found=False)
                        above_max_size_found = True
        # TODO: figure out how to move this logic into the search_state filters instead
        return TorrentMatch(torrent_entry=None, above_max_size_found=above_max_size_found)

    def _resolve_lfm_album_info(self, si: SearchItem) -> LFMAlbumInfo | None:
        try:
            lfm_api_response = self._lfm_client.request_api(
                method="album.getinfo",
                params=f"artist={si.initial_info.encoded_artist_str}&album={si.initial_info.encoded_entity_str}",
            )
            lfmai = LFMAlbumInfo.construct_from_api_response(json_blob=lfm_api_response)
        except LFMClientException:  # pragma: no cover
            _LOGGER.debug(f"LFMClientException encountered during LFM album info resolution for search item: {si}")
            lfmai = None
        return lfmai

    def _resolve_lfm_track_info(self, si: SearchItem) -> SearchItem:
        """
        Method that attempts to resolve the origin release that a track rec came from (in order to search for the release on RED).
        First checks if the LFM API has a album associated with the track, if not, searches musicbrainz with the track info on hand,
        and ideally with at least the track artist's musicbrainz artist ID. If there's no resolved release from
        both the LFM API search AND the musicbrainz search, skip the recommendation.
        """
        _LOGGER.debug(f"Resolving LFM track info for {str(si)} ({si.initial_info.lfm_entity_url}) ...")
        try:
            lfm_api_response = self._lfm_client.request_api(
                method="track.getinfo",
                params=f"artist={si.initial_info.encoded_artist_str}&track={si.initial_info.encoded_entity_str}",
            )
            if lfm_api_response and "album" in lfm_api_response:
                resolved_track_info = LFMTrackInfo.construct_from_api_response(json_blob=lfm_api_response)
                si.set_lfm_track_info(lfmti=resolved_track_info)
                return si
        except LFMClientException:  # pragma: no cover
            _LOGGER.debug(f"LFMClientException encountered during track origin release resolution: {si}")
            lfm_api_response = None

        mb_origin_release_info = self._musicbrainz_client.request_release_details_for_track(
            human_readable_track_name=si.track_name,
            artist_mbid=None if not lfm_api_response else lfm_api_response.get("artist", {"mbid": None}).get("mbid"),
            human_readable_artist_name=si.artist_name,
        )
        si.set_lfm_track_info(
            lfmti=(
                None
                if not mb_origin_release_info
                else LFMTrackInfo.from_mb_origin_release_info(si=si, mb_origin_release_info_json=mb_origin_release_info)
            )
        )
        return si

    def _attempt_resolve_mb_release(self, si: SearchItem) -> SearchItem:
        if mbid := si.get_matched_mbid():
            _LOGGER.debug(f"Searching musicbrainz for release-mbid: '{mbid}'")
            try:
                mb_response_json = self._musicbrainz_client.request_release_details(mbid=mbid)
                si.set_mb_release(MBRelease.construct_from_api(json_blob=mb_response_json))
            except (MusicBrainzClientException, KeyError):  # pragma: no cover
                _LOGGER.error(f"Musicbrainz resolution error for search item '{si}'.", exc_info=True)
        else:
            _LOGGER.debug(f"No MBID to resolve from for artist: '{si.artist_name}', release: '{si.release_name}'")
        return si

    def _search_for_release_te(self, si: SearchItem, rich_progress: NestedProgress) -> SearchItem | None:
        """
        Searches for the recommended release, and returns a tuple containing the permalink for the best RED match
        and the release mbid (if an mbid is found / the app is configured to request an mbid from LFM's API)
        according to format_preferences, search preferences, and snatch preferences.
        Returns None if no viable match is found.
        """
        if not self._search_state.pre_mbid_resolution_filter(si=si):
            return None
        # If filtering the RED searches by any of these fields, then grab the release mbid from LFM, then hit musicbrainz to get the relevant data fields.
        # TODO: allow per-manual search adjustment of what fields (if any) to resolve from MB
        if (not si.is_manual) and self._search_state.requires_mbid_resolution():
            if si.initial_info.entity_type == EntityType.ALBUM:
                si.set_lfm_album_info(self._resolve_lfm_album_info(si=si))
            si = self._attempt_resolve_mb_release(si=si)
            if not self._search_state.post_mbid_resolution_filter(si=si):
                _LOGGER.debug(
                    f"Could not resolve MBID release for artist: '{si.artist_name}',  entity: '{si.initial_info.entity_type}' ({si.initial_info.entity_type})"
                )
                return None

        torrent_match = self._search_red_release_by_preferences(si=si, rich_progress=rich_progress)
        si.set_torrent_match_fields(torrent_match=torrent_match)
        if not self._search_state.post_red_search_filter(si=si):
            return None
        return si

    def _search(self, search_items: list[SearchItem]) -> None:
        """
        Iterate over the list of SearchItems and search for a TE match on RED for each one.
        Updates the SearchState with the valid and/or skipped recs as it searches.
        """
        if not search_items:
            _LOGGER.warning("Input search_items list is empty. Skipping search.")
            return
        rec_type = search_items[0].initial_info.entity_type
        if not all([si.initial_info.entity_type == rec_type for si in search_items]):
            raise ReleaseSearcherException("All search items must be of same entity_type.")
        # initialize the db records for each search item
        self._search_state.initialize_search_records(initial_search_items=search_items)
        # with Progress(*prog_args(), **prog_kwargs()) as progress:
        with NestedProgress() as progress:
            for si in progress.track(search_items, description=f"[magenta]Searching {rec_type} recs"):
                augmented_si = self._search_for_release_te(si=si, rich_progress=progress)
                if augmented_si and augmented_si.found_red_match():
                    self._search_state.add_search_item_to_snatch(si=augmented_si)

    def _search_for_track_recs(self, search_items: list[SearchItem]) -> None:
        """
        Iterate over the list of track-rec-based SearchItems recs and first resolve the release the track
        originates from, then search for each one on RED. Returns the list of RED permalinks which match
        the search criteria for the given SearchItem.
        """
        if not search_items:
            _LOGGER.warning("Input search_items list is empty. Skipping search.")
            return
        resolved_track_search_items = []
        # with Progress(*prog_args(), **prog_kwargs()) as progress:
        with NestedProgress() as progress:
            for si in progress.track(search_items, description="Resolving release details for track recs"):
                si_with_track_info = self._resolve_lfm_track_info(si=si)
                if self._search_state.post_resolve_track_filter(si=si_with_track_info):
                    resolved_track_search_items.append(si_with_track_info)
        self._search(search_items=resolved_track_search_items)

    def search_for_recs(self, rec_type_to_recs_list: dict[EntityType, list[LFMRec]]) -> None:
        """
        Search for all enabled rec_types scraped from LFM. Then snatch the recs if snatching is enabled.
        """
        if not self._search_state.red_user_details_is_initialized():
            self._gather_red_user_details()
        if EntityType.ALBUM in rec_type_to_recs_list:
            self._search(search_items=[SearchItem(initial_info=rec) for rec in rec_type_to_recs_list[EntityType.ALBUM]])
        if EntityType.TRACK in rec_type_to_recs_list:
            self._search_for_track_recs(
                search_items=[SearchItem(initial_info=rec) for rec in rec_type_to_recs_list[EntityType.TRACK]]
            )
        if self._run_cache.enabled:
            self._run_cache.close()
        self._snatch_matches()

    def manual_search(self, search_id: int, mbid: str | None = None) -> None:
        """Public method that the manual search endpoint should invoke. Not used by the scraper."""
        # TODO: use different class for manual searches than lfmrec
        db_initial_result = get_result_by_id(search_id=search_id)
        manual_search_instance = ManualSearch(
            entity_type=db_initial_result.entity_type,
            artist=db_initial_result.artist,
            entity=db_initial_result.entity,
            mbid=mbid,
        )
        if not self._search_state.red_user_details_is_initialized():
            self._gather_red_user_details()
        search_items = [SearchItem(initial_info=manual_search_instance, is_manual=True, search_id=search_id)]
        if manual_search_instance.entity_type == EntityType.ALBUM:
            self._search(search_items=search_items)
        elif manual_search_instance.entity_type == EntityType.TRACK:
            self._search_for_track_recs(search_items=search_items)
        if self._run_cache.enabled:
            self._run_cache.close()
        # TODO: make sure this function only snatches the manual item and ignores any queued state from scrape runs
        self._snatch_matches(manual_run=True)

    def _snatch_matches(self, manual_run: bool = False) -> None:
        if not self._enable_snatches:
            _LOGGER.warning("Not configured to snatch. Please update your config to enable.")
            return
        if search_items_to_snatch := self._search_state.get_search_items_to_snatch(manual_run=manual_run):
            _LOGGER.debug(f"Beginning to snatch matched torrents to download directory '{self._snatch_directory}' ...")
            with NestedProgress() as progress:
                for si_to_snatch in progress.track(search_items_to_snatch, description="Snatching matched torrents"):
                    self._snatch_match(si_to_snatch=si_to_snatch)
        else:
            _LOGGER.warning("No torrents matched to your LFM recs. Consider adjusting the search config preferences.")

    def _snatch_match(self, si_to_snatch: SearchItem) -> None:
        te_to_snatch = si_to_snatch.torrent_entry
        if not te_to_snatch:  # pragma: no cover
            _LOGGER.error("SearchItem marked for snatching unexpected missing torrent entry: ")
            return
        tid = te_to_snatch.torrent_id
        permalink = te_to_snatch.get_permalink_url()
        out_filepath = os.path.join(self._snatch_directory, f"{tid}.torrent")
        exc_name: str | None = None
        _LOGGER.debug(f"Snatching {permalink} and saving to {out_filepath} ...")
        try:
            binary_contents = self._red_snatch_client.snatch(tid=str(tid), can_use_token=te_to_snatch.can_use_token)
            with open(out_filepath, "wb") as f:
                f.write(binary_contents)
        except Exception as ex:
            # Delete any potential file artifacts in case the failure took place in the middle of the .torrent file writing.
            if os.path.exists(out_filepath):
                os.remove(out_filepath)
            _LOGGER.error(f"Failed to snatch due to uncaught error for: {permalink}: ", exc_info=True)
            exc_name = ex.__class__.__name__
        finally:
            fl_token_used = self._red_snatch_client.tid_snatched_with_fl_token(tid=tid)
            self._search_state.add_snatch_final_status_row(
                si=si_to_snatch, snatched_with_fl=fl_token_used, snatch_path=out_filepath, exc_name=exc_name
            )
