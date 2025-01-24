import logging
import os
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import quote_plus

from tqdm import tqdm

from plastered.config.config_parser import AppConfig
from plastered.run_cache.run_cache import CacheType, RunCache
from plastered.scraper.lfm_scraper import LFMRec, RecContext, RecommendationType
from plastered.stats.stats import (
    SkippedReason,
    SnatchFailureReason,
    print_and_save_all_searcher_stats,
)
from plastered.utils.constants import STATS_TRACK_REC_NONE
from plastered.utils.exceptions import LFMClientException, ReleaseSearcherException
from plastered.utils.http_utils import LFMAPIClient, MusicBrainzAPIClient, RedAPIClient
from plastered.utils.lfm_utils import LFMAlbumInfo, LFMTrackInfo
from plastered.utils.musicbrainz_utils import MBRelease
from plastered.utils.red_utils import (
    RedFormat,
    RedUserDetails,
    ReleaseEntry,
    TorrentEntry,
)

_LOGGER = logging.getLogger(__name__)


def require_mbid_resolution(
    use_release_type: bool, use_first_release_year: bool, use_record_label: bool, use_catalog_number: bool
) -> bool:
    return use_release_type or use_first_release_year or use_record_label or use_catalog_number


class ReleaseSearcher:
    """
    General 'brains' for searching for a collection of LFM-recommended releases.
    Responsible for ultimately searching, filtering, and downloading matching releases from RED.
    Optionally may interact with the official LFM API to collect the MBID for a release, and may also optionally
    interact with the official MusicBrainz API to gather more specific search parameters to use on the RED browse endpoint.
    """

    def __init__(self, app_config: AppConfig):
        self._red_user_id = app_config.get_cli_option("red_user_id")
        self._red_user_details: Optional[RedUserDetails] = None
        self._skip_prior_snatches = app_config.get_cli_option("skip_prior_snatches")
        self._allow_library_items = app_config.get_cli_option("allow_library_items")
        self._output_summary_dir_path = app_config.get_output_summary_dir_path()
        self._enable_snatches = app_config.get_cli_option("snatch_recs")
        self._snatch_directory = app_config.get_cli_option("snatch_directory")
        self._use_release_type = app_config.get_cli_option("use_release_type")
        self._use_first_release_year = app_config.get_cli_option("use_first_release_year")
        self._use_record_label = app_config.get_cli_option("use_record_label")
        self._use_catalog_number = app_config.get_cli_option("use_catalog_number")
        self._require_mbid_resolution = require_mbid_resolution(
            use_release_type=self._use_release_type,
            use_first_release_year=self._use_first_release_year,
            use_record_label=self._use_record_label,
            use_catalog_number=self._use_catalog_number,
        )
        self._run_cache = RunCache(app_config=app_config, cache_type=CacheType.API)
        self._red_client = RedAPIClient(app_config=app_config, run_cache=self._run_cache)
        self._lfm_client = LFMAPIClient(app_config=app_config, run_cache=self._run_cache)
        self._musicbrainz_client = MusicBrainzAPIClient(app_config=app_config, run_cache=self._run_cache)
        self._red_format_preferences = app_config.get_red_preference_ordering()
        self._max_size_gb = app_config.get_cli_option("max_size_gb")
        self._snatch_summary_rows: List[List[str]] = []
        self._skipped_snatch_summary_rows: List[List[str]] = []
        self._failed_snatches_summary_rows: List[List[str]] = []
        self._tids_to_snatch: Set[int] = set()
        self._torrent_entries_to_snatch: List[TorrentEntry] = []

    def _gather_red_user_details(self) -> None:
        _LOGGER.info(f"Gathering red user details to help with search filtering ...")
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
        self._red_user_details = RedUserDetails(
            user_id=self._red_user_id,
            snatched_count=snatched_torrent_count,
            snatched_torrents_list=snatched_user_torrents_json + seeding_user_torrents_json,
        )

    def _add_skipped_snatch_row(self, rec: LFMRec, reason: SkippedReason, matched_tid: Optional[int] = None) -> None:
        self._skipped_snatch_summary_rows.append(
            [
                rec.rec_type.value,
                rec.rec_context.value,
                rec.get_human_readable_artist_str(),
                rec.get_human_readable_release_str(),
                (
                    STATS_TRACK_REC_NONE
                    if rec.rec_type == RecommendationType.ALBUM
                    else rec.get_human_readable_entity_str()
                ),
                str(matched_tid),
                reason.value,
            ]
        )

    def _add_failed_snatch_row(self, te: TorrentEntry, exception_class_name: str) -> None:
        snatch_failure_reason = SnatchFailureReason.OTHER
        if (
            exception_class_name == SnatchFailureReason.RED_API_REQUEST_ERROR
            or exception_class_name == SnatchFailureReason.FILE_ERROR
        ):
            snatch_failure_reason = SnatchFailureReason(exception_class_name)
        self._failed_snatches_summary_rows.append(
            [te.get_permalink_url(), te.get_matched_mbid(), snatch_failure_reason.value]
        )

    def _add_snatch_row(self, te: TorrentEntry, snatch_path: str) -> None:
        self._snatch_summary_rows.append(
            [
                str(te.get_lfm_rec_type()),
                str(te.get_lfm_rec_context()),
                str(te.get_artist_name()),
                str(te.get_release_name()),
                str(STATS_TRACK_REC_NONE if not te.get_track_rec_name() else te.get_track_rec_name()),
                str(te.torrent_id),
                str(te.media),
                str("yes" if self._red_client.tid_snatched_with_fl_token(tid=te.torrent_id) else "no"),
                str(snatch_path),
            ],
        )
        pass  # TODO:

    # pylint: disable=redefined-builtin
    def create_red_browse_params(self, red_format: RedFormat, lfm_rec: LFMRec, **search_kwargs) -> str:
        """Utility method for creating the RED browse API params string"""
        artist_name = lfm_rec.artist_str
        album_name = lfm_rec.release_str
        format = red_format.get_format()
        encoding = red_format.get_encoding()
        media = red_format.get_media()
        # TODO: figure out why the `order_by` param appears to be ignored whenever the params also have `group_results=1`.
        browse_request_params = f"artistname={artist_name}&groupname={album_name}&format={format}&encoding={encoding}&media={media}&group_results=1&order_by=seeders&order_way=desc"
        release_type = search_kwargs.get("release_type") if self._use_release_type else None
        first_release_year = search_kwargs.get("first_release_year") if self._use_first_release_year else None
        record_label = search_kwargs.get("record_label") if self._use_record_label else None
        catalog_number = search_kwargs.get("catalog_number") if self._use_catalog_number else None
        if release_type:
            browse_request_params += f"&releasetype={release_type.value}"
        if first_release_year:
            browse_request_params += f"&year={first_release_year}"
        if record_label:
            browse_request_params += f"&recordlabel={quote_plus(record_label)}"
        if catalog_number:
            browse_request_params += f"&cataloguenumber={quote_plus(catalog_number)}"
        return browse_request_params

    def _search_red_release_by_preferences(self, lfm_rec: LFMRec, **search_kwargs) -> Optional[TorrentEntry]:
        above_max_size_found = False
        for pref in self._red_format_preferences:
            browse_request_params = self.create_red_browse_params(
                red_format=pref, lfm_rec=lfm_rec, search_kwargs=search_kwargs
            )
            try:
                red_browse_response = self._red_client.request_api(action="browse", params=browse_request_params)
            except Exception:
                _LOGGER.error(f"Uncaught exception during RED browse request: {browse_request_params}: ", exc_info=True)
                continue
            release_entries_browse_response = [
                ReleaseEntry.from_torrent_search_json_blob(json_blob=result_blob)
                for result_blob in red_browse_response["results"]
            ]

            # Find best torrent entry
            for release_entry in release_entries_browse_response:
                for torrent_entry in release_entry.get_torrent_entries():
                    size_gb = torrent_entry.get_size(unit="GB")
                    if size_gb <= self._max_size_gb:
                        return torrent_entry
                    above_max_size_found = True
        skip_reason = SkippedReason.ABOVE_MAX_SIZE if above_max_size_found else SkippedReason.NO_MATCH_FOUND
        self._add_skipped_snatch_row(rec=lfm_rec, reason=skip_reason)
        return None

    def _resolve_lfm_album_info(self, lfm_rec: LFMRec) -> LFMAlbumInfo:
        return LFMAlbumInfo.construct_from_api_response(
            json_blob=self._lfm_client.request_api(
                method="album.getinfo",
                params=f"artist={lfm_rec.artist_str}&album={lfm_rec.entity_str}",
            )
        )

    def _resolve_lfm_track_info(self, lfm_rec: LFMRec) -> Optional[LFMTrackInfo]:
        """
        Method that attempts to resolve the origin release that a track rec came from (in order to search for the release on RED).
        First checks if the LFM API has a album associated with the track, if not, searches musicbrainz with the track info on hand,
        and ideally with at least the track artist's musicbrainz artist ID. If there's not resolved release from
        both the LFM API search AND the musicbrainz search, skip the recommendation.
        """
        _LOGGER.debug(f"Resolving LFM track info for {str(lfm_rec)} ({lfm_rec.lfm_entity_url})...")
        track_str, artist_str = lfm_rec.get_human_readable_track_str(), lfm_rec.get_human_readable_artist_str()
        try:
            lfm_api_response = self._lfm_client.request_api(
                method="track.getinfo",
                params=f"artist={lfm_rec.artist_str}&track={lfm_rec.entity_str}",
            )
        except LFMClientException:  # pragma: no cover
            _LOGGER.debug(f"LFMClientException encountered during track origin release resolution: {lfm_rec}")
            lfm_api_response = None

        if lfm_api_response and "album" in lfm_api_response:
            return LFMTrackInfo.construct_from_api_response(json_blob=lfm_api_response)
        try:
            artist_mbid = lfm_api_response["artist"]["mbid"]
        except (KeyError, TypeError):
            _LOGGER.debug(f"No ARID found for track rec: '{track_str}' by '{artist_str}'")
            artist_mbid = None

        mb_origin_release_info = self._musicbrainz_client.request_release_details_for_track(
            human_readable_track_name=track_str,
            artist_mbid=artist_mbid,
            human_readable_artist_name=artist_str,
        )
        if not mb_origin_release_info:
            _LOGGER.debug(f"Unable to find origin release for track rec: '{track_str}' by '{artist_str}'")
            return None
        return LFMTrackInfo(
            artist=artist_str,
            track_name=track_str,
            lfm_url=lfm_rec.lfm_entity_url,
            release_mbid=mb_origin_release_info["origin_release_mbid"],
            release_name=mb_origin_release_info["origin_release_name"],
        )

    def _resolve_mb_release(self, mbid: str) -> MBRelease:
        return MBRelease.construct_from_api(
            json_blob=self._musicbrainz_client.request_release_details(entity_type="release", mbid=mbid)
        )

    def _pre_search_filter_validate(self, lfm_rec: LFMRec) -> bool:
        """
        Return True if the lfm_rec is valid to search for on the various APIs, or False if the lfm_rec should be skipped given the current app config settings.
        """
        artist = lfm_rec.get_human_readable_artist_str()
        release = lfm_rec.get_human_readable_entity_str()
        if self._skip_prior_snatches and self._red_user_details.has_snatched_release(artist=artist, release=release):
            _LOGGER.debug(f"'skip_prior_snatches' config field is set to True")
            _LOGGER.debug(
                f"Skipped - artist: '{artist}', release: '{release}' due to prior snatch found in release group"
            )
            self._add_skipped_snatch_row(rec=lfm_rec, reason=SkippedReason.ALREADY_SNATCHED)
            return False
        if not self._allow_library_items and lfm_rec.rec_context == RecContext.IN_LIBRARY:
            _LOGGER.debug(f"'allow_library_items' config field is set to {self._allow_library_items}.")
            _LOGGER.debug(
                f"Skipped - artist: '{artist}', release: '{release}'. Rec context is {RecContext.IN_LIBRARY.value}"
            )
            self._add_skipped_snatch_row(rec=lfm_rec, reason=SkippedReason.REC_CONTEXT_FILTERING)
            return False
        return True

    def _post_search_filter(self, lfm_rec: LFMRec, best_te: Optional[TorrentEntry]) -> bool:
        """
        Return True if the provided lfm_rec and corresponding matched_te is valid to add to the
        pending list of torrents to snatch, otherwise update the skipped_snatch_rows accordingly and return False.
        """
        # No match found
        if not best_te:
            _LOGGER.info(
                f"No valid RED match found for release: '{lfm_rec.get_human_readable_release_str()}' by '{lfm_rec.get_human_readable_artist_str()}'"
            )
            return False
        # Check whether the match is tied to a release which is already pending snatching during this run
        if best_te.torrent_id in self._tids_to_snatch:
            self._add_skipped_snatch_row(rec=lfm_rec, reason=SkippedReason.DUPE_OF_ANOTHER_REC)
            return False
        # Check whether the match's TID is already in the user's snatched / seeding TIDs.
        if self._red_user_details.has_snatched_tid(tid=best_te.torrent_id):
            self._add_skipped_snatch_row(
                rec=lfm_rec, reason=SkippedReason.ALREADY_SNATCHED, matched_tid=best_te.torrent_id
            )
            return False
        return True

    def search_for_release_rec(self, lfm_rec: LFMRec, release_mbid: Optional[str] = None) -> Optional[TorrentEntry]:
        """
        Searches for the recommended release, and returns a tuple containing the permalink for the best RED match
        and the release mbid (if an mbid is found / the app is configured to request an mbid from LFM's API)
        according to format_preferences, search preferences, and snatch preferences.
        Returns None if no viable match is found.
        """
        if not self._pre_search_filter_validate(lfm_rec=lfm_rec):
            return None
        artist = lfm_rec.get_human_readable_artist_str()
        release = lfm_rec.get_human_readable_release_str()
        # If filtering the RED searches by any of these fields, then grab the release mbid from LFM, then hit musicbrainz to get the relevant data fields.
        search_kwargs = {}
        if self._require_mbid_resolution:
            if lfm_rec.rec_type == RecommendationType.ALBUM:
                lfm_album_info = self._resolve_lfm_album_info(lfm_rec=lfm_rec)
                release_mbid = lfm_album_info.get_release_mbid()
            if release_mbid:
                _LOGGER.debug(
                    f"Attempting musicbrainz query for artist: {artist}, release: '{release}', release-mbid: '{release_mbid}'"
                )
                mb_release = self._resolve_mb_release(mbid=release_mbid)
                search_kwargs = mb_release.get_release_searcher_kwargs()
            else:  # pragma: no cover
                _LOGGER.debug(f"LFM gave no MBID for artist: '{artist}', release: '{release}'")

        best_torrent_entry = self._search_red_release_by_preferences(lfm_rec=lfm_rec, search_kwargs=search_kwargs)
        if not self._post_search_filter(lfm_rec=lfm_rec, best_te=best_torrent_entry):
            return None
        best_torrent_entry.set_matched_mbid(matched_mbid=release_mbid)
        best_torrent_entry.set_lfm_rec_fields(
            rec_type=lfm_rec.rec_type.value,
            rec_context=lfm_rec.rec_context.value,
            artist_name=artist,
            release_name=release,
            track_rec_name=None if lfm_rec.is_album_rec else lfm_rec.get_human_readable_track_str(),
        )
        return best_torrent_entry

    def _get_tid_and_snatch_path(self, permalink: str) -> Tuple[str, str]:
        tid = permalink.split("=")[-1]
        return tid, os.path.join(self._snatch_directory, f"{tid}.torrent")

    def _search_for_release_recs(self, lfm_recs: List[LFMRec]) -> None:
        """
        Iterate over the list of recs and search for each one on RED.
        Returns the list of RED permalinks which match the search criteria for the given LFMRecs.
        """
        if not lfm_recs:
            _LOGGER.warning(f"Input lfm_recs list is empty. Skipping search.")
            return
        rec_type = lfm_recs[0].rec_type.value
        if not all([lfm_rec.rec_type.value == rec_type for lfm_rec in lfm_recs]):
            raise ReleaseSearcherException(
                f"Invalid lfm_recs list. All recs in list must have the same rec_type value. Must be either '{RecommendationType.ALBUM.value}'or '{RecommendationType.TRACK.value}'"
            )
        if self._skip_prior_snatches and self._red_user_details is None:
            raise ReleaseSearcherException(
                f"self._skip_prior_snatches set to {self._skip_prior_snatches}, but self._red_user_details has not yet been populated."
            )
        # Required so that tqdm doesnt break logging: https://stackoverflow.com/a/69145493
        # with logging_redirect_tqdm(loggers=[_LOGGER, RUN_CACHE_LOGGER, HTTP_UTILS_LOGGER]):
        for rec in tqdm(lfm_recs, desc=f"Searching {rec_type} recs"):
            if rec_type == RecommendationType.ALBUM.value:
                matched_torrent_entry = self.search_for_release_rec(lfm_rec=rec)
            else:
                matched_torrent_entry = self.search_for_release_rec(
                    lfm_rec=rec, release_mbid=rec.track_origin_release_mbid
                )
            if not matched_torrent_entry:
                continue
            self._tids_to_snatch.add(matched_torrent_entry.torrent_id)
            self._torrent_entries_to_snatch.append(matched_torrent_entry)
        if self._run_cache.enabled:
            self._run_cache.close()

    def _search_for_track_recs(self, track_recs: List[LFMRec]) -> None:
        """
        Iterate over the list of LFM track recs and first resolve the release the track originates from,
        then search for each one on RED. Returns the list of RED permalinks which match the search criteria
        for the given LFMRec.
        """
        # Required so that tqdm doesnt break logging: https://stackoverflow.com/a/69145493
        resolved_track_recs = []
        # with logging_redirect_tqdm(loggers=[_LOGGER, RUN_CACHE_LOGGER, HTTP_UTILS_LOGGER]):
        for track_rec in tqdm(track_recs, desc="Resolving track recs"):
            lfm_track_info = self._resolve_lfm_track_info(lfm_rec=track_rec)
            if not lfm_track_info:
                self._add_skipped_snatch_row(rec=track_rec, reason=SkippedReason.NO_SOURCE_RELEASE_FOUND)
                continue
            track_rec.set_track_origin_release(track_origin_release=lfm_track_info.get_release_name())
            track_rec.set_track_origin_release_mbid(track_origin_release_mbid=lfm_track_info.get_release_mbid())
            resolved_track_recs.append(track_rec)
        self._search_for_release_recs(lfm_recs=resolved_track_recs)

    def search_for_recs(self, rec_type_to_recs_list: Dict[RecommendationType, List[LFMRec]]) -> None:
        """
        Search for all enabled rec_types scraped from LFM. Then snatch the recs if snatching is enabled.
        """
        self._gather_red_user_details()
        if RecommendationType.ALBUM in rec_type_to_recs_list:
            self._search_for_release_recs(lfm_recs=rec_type_to_recs_list[RecommendationType.ALBUM])
        if RecommendationType.TRACK in rec_type_to_recs_list:
            self._search_for_track_recs(track_recs=rec_type_to_recs_list[RecommendationType.TRACK])
        self._snatch_matches()

    def _snatch_matches(self) -> None:
        if not self._enable_snatches:
            _LOGGER.warning(f"Not configured to snatch. Please update your config to enable.")
            return
        if not self._torrent_entries_to_snatch:
            _LOGGER.warning(
                f"No eligible torrents were matched to your LFM recs. Consider adjusting your search config preferences."
            )
            return
        _LOGGER.debug(f"Beginning to snatch matched permalinks to download directory '{self._snatch_directory}' ...")
        # Prepare a list of to-snatch torrents in descending size to ensure FL tokens are used optimally (if FL token usage is enabled).
        to_snatch = sorted(self._torrent_entries_to_snatch, key=lambda te: te.get_size(unit="MB"), reverse=True)
        # Required so that tqdm doesnt break logging: https://stackoverflow.com/a/69145493
        # with logging_redirect_tqdm(loggers=[_LOGGER, RUN_CACHE_LOGGER, HTTP_UTILS_LOGGER]):
        for torrent_entry_to_snatch in tqdm(to_snatch, desc="Snatching matched torrents"):
            permalink = torrent_entry_to_snatch.get_permalink_url()
            tid, out_filepath = self._get_tid_and_snatch_path(permalink=permalink)
            _LOGGER.debug(f"Snatching {permalink} and saving to {out_filepath} ...")
            try:
                binary_contents = self._red_client.snatch(
                    tid=tid,
                    can_use_token_on_torrent=torrent_entry_to_snatch.token_usable(),
                )
                with open(out_filepath, "wb") as f:
                    f.write(binary_contents)
            except Exception as ex:
                # Delete any potential file artifacts in case the failure took place in the middle of the .torrent file writing.
                if os.path.exists(out_filepath):
                    os.remove(out_filepath)
                _LOGGER.error(
                    f"Failed to snatch - uncaught error during snatch attempt for: {permalink}: ", exc_info=True
                )
                self._add_failed_snatch_row(te=torrent_entry_to_snatch, exception_class_name=ex.__class__.__name__)
                continue
            self._add_snatch_row(te=torrent_entry_to_snatch, snatch_path=out_filepath)

    def generate_summary_stats(self) -> None:
        print_and_save_all_searcher_stats(
            skipped_rows=self._skipped_snatch_summary_rows,
            failed_snatch_rows=self._failed_snatches_summary_rows,
            snatch_summary_rows=self._snatch_summary_rows,
            output_summary_dir_path=self._output_summary_dir_path,
        )
