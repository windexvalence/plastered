import logging
import os
from collections import namedtuple
from typing import Dict, List, Optional

from tqdm import tqdm

from plastered.config.config_parser import AppConfig
from plastered.release_search.search_helpers import SearchItem, SearchState
from plastered.run_cache.run_cache import CacheType, RunCache
from plastered.scraper.lfm_scraper import LFMRec, RecommendationType
from plastered.utils.exceptions import LFMClientException, ReleaseSearcherException
from plastered.utils.httpx_utils import (
    LFMAPIClient,
    MusicBrainzAPIClient,
    RedAPIClient,
    RedSnatchAPIClient,
)
from plastered.utils.lfm_utils import LFMAlbumInfo, LFMTrackInfo
from plastered.utils.musicbrainz_utils import MBRelease
from plastered.utils.red_utils import RedUserDetails, ReleaseEntry

_LOGGER = logging.getLogger(__name__)


_TorrentMatch = namedtuple("_TorrentMatch", ["torrent_entry", "above_max_size_found"])


class ReleaseSearcher:
    """
    General 'brains' for searching for a collection of LFM-recommended releases.
    Responsible for ultimately searching, filtering, and downloading matching releases from RED.
    Optionally may interact with the official LFM API to collect the MBID for a release, and may also optionally
    interact with the official MusicBrainz API to gather more specific search parameters to use on the RED browse endpoint.
    """

    def __init__(self, app_config: AppConfig):
        self._run_cache = RunCache(app_config=app_config, cache_type=CacheType.API)
        self._red_client: Optional[RedAPIClient] = None
        self._red_snatch_client: Optional[RedSnatchAPIClient] = None
        self._lfm_client: Optional[LFMAPIClient] = None
        self._musicbrainz_client: Optional[MusicBrainzAPIClient] = None
        self._red_user_id = app_config.get_cli_option("red_user_id")
        self._search_state = SearchState(app_config=app_config)
        self._enable_snatches = app_config.get_cli_option("snatch_recs")
        self._snatch_directory = app_config.get_cli_option("snatch_directory")
        self._app_config = app_config

    def __enter__(self):
        _LOGGER.debug("Initializing API client sessions ...")
        self._red_client = RedAPIClient(app_config=self._app_config, run_cache=self._run_cache)
        self._red_snatch_client = RedSnatchAPIClient(app_config=self._app_config, run_cache=self._run_cache)
        self._lfm_client = LFMAPIClient(app_config=self._app_config, run_cache=self._run_cache)
        self._musicbrainz_client = MusicBrainzAPIClient(app_config=self._app_config, run_cache=self._run_cache)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:  # pragma: no cover
            _LOGGER.error("ReleaseSearcher encountered an uncaught exception", exc_info=True)
        self._run_cache.close()
        if self._red_client:
            self._red_client.close_session()
        if self._red_snatch_client:
            self._red_snatch_client.close_session()
        if self._lfm_client:
            self._lfm_client.close_session()
        if self._musicbrainz_client:
            self._musicbrainz_client.close_session()

    # TODO (later): make this method call happen exclusively within the __enter__ method
    def _gather_red_user_details(self) -> None:
        _LOGGER.info("Gathering red user details to help with search filtering and ratio calculations ...")
        user_stats_json = self._red_client.request_api(action="community_stats", params=f"userid={self._red_user_id}")
        snatched_torrent_count = int(user_stats_json["snatched"].replace(",", ""))
        seeding_torrent_count = int(user_stats_json["seeding"].replace(",", ""))
        snatched_user_torrents_json = self._red_client.request_api(
            action="user_torrents",
            params=f"id={self._red_user_id}&type=snatched&limit={snatched_torrent_count}&offset=0",
        )["snatched"]
        seeding_user_torrents_json = self._red_client.request_api(
            action="user_torrents",
            params=f"id={self._red_user_id}&type=seeding&limit={seeding_torrent_count}&offset=0",
        )["seeding"]
        user_profile_json = self._red_client.request_api(action="user", params=f"id={self._red_user_id}")
        red_user_details = RedUserDetails(
            user_id=self._red_user_id,
            snatched_count=snatched_torrent_count,
            snatched_torrents_list=snatched_user_torrents_json + seeding_user_torrents_json,
            user_profile_json=user_profile_json,
        )
        self._red_snatch_client.set_initial_available_fl_tokens(
            initial_available_fl_tokens=red_user_details.get_initial_available_fl_tokens()
        )
        self._search_state.set_red_user_details(red_user_details=red_user_details)

    def _search_red_release_by_preferences(self, si: SearchItem) -> _TorrentMatch:
        above_max_size_found = False
        for pref in self._search_state.red_format_preferences:
            browse_request_params = self._search_state.create_red_browse_params(red_format=pref, si=si)
            try:
                red_browse_response = self._red_client.request_api(action="browse", params=browse_request_params)
            except Exception:
                _LOGGER.error(f"Uncaught exception during RED browse request: {browse_request_params}: ", exc_info=True)
                continue
            release_entries_browse_response = [
                ReleaseEntry.from_torrent_search_json_blob(json_blob=result_blob)
                for result_blob in red_browse_response["results"]
            ]

            # Find best entry from the RED browse response
            for release_entry in release_entries_browse_response:
                for torrent_entry in release_entry.get_torrent_entries():
                    size_gb = torrent_entry.get_size(unit="GB")
                    if size_gb <= self._search_state.max_size_gb:
                        return _TorrentMatch(torrent_entry=torrent_entry, above_max_size_found=False)
                    above_max_size_found = True
        # TODO: figure out how to move this logic into the search_state filters instead
        return _TorrentMatch(torrent_entry=None, above_max_size_found=above_max_size_found)

    def _resolve_lfm_album_info(self, si: SearchItem) -> LFMAlbumInfo:
        return LFMAlbumInfo.construct_from_api_response(
            json_blob=self._lfm_client.request_api(
                method="album.getinfo",
                params=f"artist={si.lfm_rec.artist_str}&album={si.lfm_rec.entity_str}",
            )
        )

    def _resolve_lfm_track_info(self, si: SearchItem) -> Optional[LFMTrackInfo]:
        """
        Method that attempts to resolve the origin release that a track rec came from (in order to search for the release on RED).
        First checks if the LFM API has a album associated with the track, if not, searches musicbrainz with the track info on hand,
        and ideally with at least the track artist's musicbrainz artist ID. If there's not resolved release from
        both the LFM API search AND the musicbrainz search, skip the recommendation.
        """
        _LOGGER.debug(f"Resolving LFM track info for {str(si)} ({si.lfm_rec.lfm_entity_url})...")
        try:
            lfm_api_response = self._lfm_client.request_api(
                method="track.getinfo",
                params=f"artist={si.lfm_rec.artist_str}&track={si.lfm_rec.entity_str}",
            )
        except LFMClientException:  # pragma: no cover
            _LOGGER.debug(f"LFMClientException encountered during track origin release resolution: {si}")
            lfm_api_response = None

        if lfm_api_response and "album" in lfm_api_response:
            return LFMTrackInfo.construct_from_api_response(json_blob=lfm_api_response)
        try:
            artist_mbid = lfm_api_response["artist"]["mbid"]
        except (KeyError, TypeError):
            _LOGGER.debug(f"No ARID found for track rec: '{si.track_name}' by '{si.artist_name}'")
            artist_mbid = None

        mb_origin_release_info = self._musicbrainz_client.request_release_details_for_track(
            human_readable_track_name=si.track_name,
            artist_mbid=artist_mbid,
            human_readable_artist_name=si.artist_name,
        )
        if not mb_origin_release_info:
            _LOGGER.debug(f"Unable to find origin release for track rec: '{si.track_name}' by '{si.artist_name}'")
            return None
        return LFMTrackInfo(
            artist=si.artist_name,
            track_name=si.track_name,
            lfm_url=si.lfm_rec.lfm_entity_url,
            release_mbid=mb_origin_release_info["origin_release_mbid"],
            release_name=mb_origin_release_info["origin_release_name"],
        )

    def _resolve_mb_release(self, mbid: str) -> MBRelease:
        _LOGGER.debug(f"Searching musicbrainz for release-mbid: '{mbid}'")
        return MBRelease.construct_from_api(json_blob=self._musicbrainz_client.request_release_details(mbid=mbid))

    def _search_for_release_te(self, si: SearchItem) -> Optional[SearchItem]:
        """
        Searches for the recommended release, and returns a tuple containing the permalink for the best RED match
        and the release mbid (if an mbid is found / the app is configured to request an mbid from LFM's API)
        according to format_preferences, search preferences, and snatch preferences.
        Returns None if no viable match is found.
        """
        if not self._search_state.pre_search_filter(si=si):
            return None
        # If filtering the RED searches by any of these fields, then grab the release mbid from LFM, then hit musicbrainz to get the relevant data fields.
        if self._search_state.requires_mbid_resolution():
            if si.lfm_rec.rec_type == RecommendationType.ALBUM:
                si.set_lfm_album_info(self._resolve_lfm_album_info(si=si))
            if si.get_matched_mbid():
                si.set_mb_release(self._resolve_mb_release(mbid=si.get_matched_mbid()))
            else:  # pragma: no cover
                _LOGGER.debug(f"LFM gave no MBID for artist: '{si.artist_name}', release: '{si.release_name}'")
                # TODO: see if this condition should return None since resolution was required but not possible

        torrent_match = self._search_red_release_by_preferences(si=si)
        si.set_torrent_match_fields(torrent_match=torrent_match)
        if not self._search_state.post_search_filter(si=si):
            return None
        return si

    def _search(self, search_items: List[SearchItem]) -> None:
        """
        Iterate over the list of SearchItems and search for a TE match on RED for each one.
        Updates the SearchState with the valid and/or skipped recs as it searches.
        """
        if not search_items:
            _LOGGER.warning(f"Input search_items list is empty. Skipping search.")
            return
        rec_type = search_items[0].lfm_rec.rec_type
        if not all([si.lfm_rec.rec_type == rec_type for si in search_items]):
            raise ReleaseSearcherException("All recs must be of same rec_type.")
        for si in tqdm(search_items, desc=f"Searching {rec_type} recs"):
            augmented_si = self._search_for_release_te(si=si)
            if augmented_si and augmented_si.found_red_match():
                self._search_state.add_search_item_to_snatch(si=augmented_si)

    def _search_for_track_recs(self, search_items: List[SearchItem]) -> None:
        """
        Iterate over the list of track-rec-based SearchItems recs and first resolve the release the track
        originates from, then search for each one on RED. Returns the list of RED permalinks which match
        the search criteria for the given SearchItem.
        """
        resolved_track_search_items = []
        for si in tqdm(search_items, desc="Resolving track recs"):
            si.set_lfm_track_info(self._resolve_lfm_track_info(si=si))
            if self._search_state.post_resolve_track_filter(si=si):
                resolved_track_search_items.append(si)
        self._search(search_items=resolved_track_search_items)

    def search_for_recs(self, rec_type_to_recs_list: Dict[RecommendationType, List[LFMRec]]) -> None:
        """
        Search for all enabled rec_types scraped from LFM. Then snatch the recs if snatching is enabled.
        """
        self._gather_red_user_details()
        if RecommendationType.ALBUM in rec_type_to_recs_list:
            self._search(
                search_items=[SearchItem(lfm_rec=rec) for rec in rec_type_to_recs_list[RecommendationType.ALBUM]],
            )
        if RecommendationType.TRACK in rec_type_to_recs_list:
            self._search_for_track_recs(
                search_items=[SearchItem(lfm_rec=rec) for rec in rec_type_to_recs_list[RecommendationType.TRACK]],
            )
        if self._run_cache.enabled:
            self._run_cache.close()
        self._snatch_matches()

    def _snatch_matches(self) -> None:
        # import pdb
        # pdb.set_trace()
        if not self._enable_snatches:
            _LOGGER.warning(f"Not configured to snatch. Please update your config to enable.")
            return
        if search_items_to_snatch := self._search_state.get_search_items_to_snatch():
            _LOGGER.debug(f"Beginning to snatch matched torrents to download directory '{self._snatch_directory}' ...")
            for si_to_snatch in tqdm(search_items_to_snatch, desc="Snatching matched torrents"):
                self._snatch_match(si_to_snatch=si_to_snatch)
        else:
            _LOGGER.warning(f"No torrents matched to your LFM recs. Consider adjusting the search config preferences.")
            return

    def _snatch_match(self, si_to_snatch: SearchItem) -> None:
        te_to_snatch = si_to_snatch.torrent_entry
        permalink = te_to_snatch.get_permalink_url()
        out_filepath = os.path.join(self._snatch_directory, f"{te_to_snatch.torrent_id}.torrent")
        exc_name = None
        _LOGGER.debug(f"Snatching {permalink} and saving to {out_filepath} ...")
        try:
            binary_contents = self._red_snatch_client.snatch(
                tid=str(te_to_snatch.torrent_id), can_use_token=te_to_snatch.token_usable()
            )
            with open(out_filepath, "wb") as f:
                f.write(binary_contents)
        except Exception as ex:
            # Delete any potential file artifacts in case the failure took place in the middle of the .torrent file writing.
            if os.path.exists(out_filepath):
                os.remove(out_filepath)
            _LOGGER.error(f"Failed to snatch due to uncaught error for: {permalink}: ", exc_info=True)
            exc_name = ex.__class__.__name__
        finally:
            self._search_state.add_snatch_final_status_row(
                si=si_to_snatch,
                snatched_with_fl=self._red_snatch_client.tid_snatched_with_fl_token(tid=te_to_snatch.torrent_id),
                snatch_path=out_filepath,
                exc_name=exc_name,
            )

    def generate_summary_stats(self) -> None:
        self._search_state.generate_summary_stats()
