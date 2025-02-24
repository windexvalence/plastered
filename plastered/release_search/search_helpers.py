import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote_plus

from plastered.config.config_parser import AppConfig
from plastered.scraper.lfm_scraper import LFMRec, RecContext, RecommendationType
from plastered.stats.stats import (
    SkippedReason,
    SnatchFailureReason,
    print_and_save_all_searcher_stats,
)
from plastered.utils.constants import STATS_TRACK_REC_NONE
from plastered.utils.lfm_utils import LFMAlbumInfo, LFMTrackInfo
from plastered.utils.musicbrainz_utils import MBRelease
from plastered.utils.red_utils import RedFormat, RedUserDetails, TorrentEntry

_LOGGER = logging.getLogger(__name__)


def _require_mbid_resolution(
    use_release_type: bool, use_first_release_year: bool, use_record_label: bool, use_catalog_number: bool
) -> bool:
    return use_release_type or use_first_release_year or use_record_label or use_catalog_number


@dataclass
class SearchItem:
    """
    Class which represents the full range of possible information that may be associated with an LFMRec over the
    duration of a search run. Ultimately, this is the individual object which most of the search functionality will work with
    and/or update during the search and filtering resolution of a given rec.
    """

    _lfm_rec: LFMRec
    above_max_size_te_found: Optional[bool] = False
    _torrent_entry: Optional[TorrentEntry] = None
    lfm_album_info: Optional[LFMAlbumInfo] = None
    lfm_track_info: Optional[LFMTrackInfo] = None
    mb_release: Optional[MBRelease] = None
    skip_reason: Optional[SkippedReason] = None
    snatch_failure_reason: Optional[SnatchFailureReason] = None

    @property
    def artist_name(self) -> str:
        """Returns the human-readable artist name."""
        return self._lfm_rec.get_human_readable_artist_str()

    @property
    def release_name(self) -> str:
        """Returns the human-readable release name."""
        return self._lfm_rec.get_human_readable_release_str()

    @property
    def track_name(self) -> str:
        """Returns the human-readable track name."""
        return self._lfm_rec.get_human_readable_track_str()

    @property
    def lfm_rec(self) -> LFMRec:
        return self._lfm_rec

    @property
    def search_kwargs(self) -> Dict[str, Any]:
        if not self.mb_release:
            return {}
        return self.mb_release.get_release_searcher_kwargs()

    @property
    def torrent_entry(self) -> Optional[TorrentEntry]:
        return self._torrent_entry

    @property
    def track_rec_name(self) -> Optional[str]:
        if self.lfm_rec.rec_type == RecommendationType.ALBUM.value:
            return STATS_TRACK_REC_NONE
        return self._torrent_entry.get_track_rec_name()

    def get_matched_mbid(self) -> Optional[str]:
        if self.lfm_rec.rec_type == RecommendationType.ALBUM:
            return None if not self.lfm_album_info else self.lfm_album_info.get_release_mbid()
        return self.lfm_track_info.get_release_mbid()

    def found_red_match(self) -> bool:
        return self._torrent_entry is not None

    @torrent_entry.setter
    def torrent_entry(self, te: TorrentEntry) -> None:
        self._torrent_entry = te
    
    def set_above_max_size_found(self, above_max_size_found: bool) -> None:
        self.above_max_size_te_found = above_max_size_found

    def set_lfm_album_info(self, lfmai: LFMAlbumInfo) -> None:
        self.lfm_album_info = lfmai

    def set_lfm_track_info(self, lfmti: LFMTrackInfo) -> None:
        self.lfm_track_info = lfmti

    def set_mb_release(self, mbr: MBRelease) -> None:
        self.mb_release = mbr


class SearchState:
    """
    Helper class which maintains the variable internal state of the searchingm process, and
    which handles the pre and post search filtering logic during a search run.
    """

    def __init__(self, app_config: AppConfig):
        self._skip_prior_snatches = app_config.get_cli_option("skip_prior_snatches")
        self._allow_library_items = app_config.get_cli_option("allow_library_items")
        self._use_release_type = app_config.get_cli_option("use_release_type")
        self._use_first_release_year = app_config.get_cli_option("use_first_release_year")
        self._use_record_label = app_config.get_cli_option("use_record_label")
        self._use_catalog_number = app_config.get_cli_option("use_catalog_number")
        self._require_mbid_resolution = _require_mbid_resolution(
            use_release_type=self._use_release_type,
            use_first_release_year=self._use_first_release_year,
            use_record_label=self._use_record_label,
            use_catalog_number=self._use_catalog_number,
        )
        self._red_format_preferences = app_config.get_red_preference_ordering()
        self._max_size_gb = app_config.get_cli_option("max_size_gb")
        self._min_allowed_ratio = app_config.get_cli_option("min_allowed_ratio")
        self._output_summary_dir_path = app_config.get_output_summary_dir_path()
        self._max_download_allowed_gb = 0.0
        self._red_user_details: Optional[RedUserDetails] = None
        self._run_download_total_gb = 0.0
        self._snatch_summary_rows: List[List[str]] = []
        self._skipped_snatch_summary_rows: List[List[str]] = []
        self._failed_snatches_summary_rows: List[List[str]] = []
        self._tids_to_snatch: Set[int] = set()
        self._torrent_entries_to_snatch: List[TorrentEntry] = []
        self._search_items_to_snatch: List[SearchItem] = []

    def set_red_user_details(self, red_user_details: RedUserDetails) -> None:
        """
        Updates the relevant information related to the RedUserDetails instance provided.
        """
        self._max_download_allowed_gb = red_user_details.calculate_max_download_allowed_gb(
            min_allowed_ratio=self._min_allowed_ratio,
        )
        self._red_user_details = red_user_details

    # pylint: disable=redefined-builtin
    def create_red_browse_params(self, red_format: RedFormat, si: SearchItem) -> str:
        """Utility method for creating the RED browse API params string"""
        artist_name = si._lfm_rec.artist_str
        album_name = si._lfm_rec.release_str
        format = red_format.get_format()
        encoding = red_format.get_encoding()
        media = red_format.get_media()
        # TODO: figure out why the `order_by` param appears to be ignored whenever the params also have `group_results=1`.
        browse_request_params = f"artistname={artist_name}&groupname={album_name}&format={format}&encoding={encoding}&media={media}&group_results=1&order_by=seeders&order_way=desc"
        release_type = si.search_kwargs.get("release_type") if self._use_release_type else None
        first_release_year = si.search_kwargs.get("first_release_year") if self._use_first_release_year else None
        record_label = si.search_kwargs.get("record_label") if self._use_record_label else None
        catalog_number = si.search_kwargs.get("catalog_number") if self._use_catalog_number else None
        if release_type:
            browse_request_params += f"&releasetype={release_type.value}"
        if first_release_year:
            browse_request_params += f"&year={first_release_year}"
        if record_label:
            browse_request_params += f"&recordlabel={quote_plus(record_label)}"
        if catalog_number:
            browse_request_params += f"&cataloguenumber={quote_plus(catalog_number)}"
        return browse_request_params

    def post_resolve_track_filter(self, si: SearchItem) -> bool:
        """
        Return True if the track-rec-based SearchItem is valid to search for on the various APIs.
        Return False otherwise if the SearchItem should be skipped given the lack of resolved origin release.
        """
        if not si.lfm_track_info:
            self._add_skipped_snatch_row(si=si, reason=SkippedReason.NO_SOURCE_RELEASE_FOUND)
            return False
        return True

    def pre_search_filter(self, si: SearchItem) -> bool:
        """
        Return True if the lfm_rec is valid to search for on the various APIs,
        or False if the lfm_rec should be skipped given the current app config settings.
        """
        artist = si.artist_name
        release = si._lfm_rec.get_human_readable_entity_str()
        if self._skip_prior_snatches and self._red_user_details.has_snatched_release(artist=artist, release=release):
            _LOGGER.debug("'skip_prior_snatches' config field is set to True")
            _LOGGER.debug(f"'{release}' by '{artist}' due to prior snatch found in release group")
            self._add_skipped_snatch_row(si=si, reason=SkippedReason.ALREADY_SNATCHED)
            return False
        if not self._allow_library_items and si.lfm_rec.rec_context == RecContext.IN_LIBRARY:
            _LOGGER.debug(f"'allow_library_items' config field is set to {self._allow_library_items}.")
            _LOGGER.debug(f"Skipped '{release}' by '{artist}'. Rec context is {RecContext.IN_LIBRARY.value}")
            self._add_skipped_snatch_row(si=si, reason=SkippedReason.REC_CONTEXT_FILTERING)
            return False
        return True

    def post_search_filter(self, si: SearchItem) -> bool:
        """
        Return True if the provided lfm_rec and corresponding matched_te is valid to add to the
        pending list of torrents to snatch, otherwise update the skipped_snatch_rows accordingly and return False.
        """
        artist = si.artist_name
        release = si._lfm_rec.get_human_readable_entity_str()
        # No match found
        if not si.found_red_match():
            _LOGGER.info(f"No valid RED match found for release: '{release}' by '{artist}'")
            skip_reason = SkippedReason.ABOVE_MAX_SIZE if si.above_max_size_te_found else SkippedReason.NO_MATCH_FOUND
            self._add_skipped_snatch_row(si=si, reason=skip_reason)
            return False
        # Check whether the match is tied to a release which is already pending snatching during this run
        if si._torrent_entry.torrent_id in self._tids_to_snatch:
            self._add_skipped_snatch_row(si=si, reason=SkippedReason.DUPE_OF_ANOTHER_REC)
            return False
        # Check whether the match's TID is already in the user's snatched / seeding TIDs.
        if self._red_user_details.has_snatched_tid(tid=si._torrent_entry.torrent_id):
            self._add_skipped_snatch_row(si=si, reason=SkippedReason.ALREADY_SNATCHED)
            return False
        return True

    def add_snatch_final_status_row(
        self, si: SearchItem, snatched_with_fl: bool, snatch_path: Optional[str], exc_name: Optional[str]
    ) -> None:
        """
        Called for any torrent once it has either been successfully snatched, or a failure during the snatch attempt took place.
        """
        if exc_name:
            self._add_failed_snatch_row(si=si, exc_name=exc_name)
            return
        self._add_snatch_success_row(si=si, snatch_path=snatch_path, snatched_with_fl=snatched_with_fl)
        self._update_run_dl_total(te=si._torrent_entry)

    def _update_run_dl_total(self, te: TorrentEntry) -> None:
        self._run_download_total_gb += te.get_size(unit="GB")

    def add_search_item_to_snatch(self, si: SearchItem) -> None:
        self._search_items_to_snatch.append(si)
        self._tids_to_snatch.add(si._torrent_entry.torrent_id)

    def requires_mbid_resolution(self) -> bool:
        return self._require_mbid_resolution

    def get_search_items_to_snatch(self) -> List[SearchItem]:
        """
        Called by the ReleaseSearcher, returns the list of SearchItems which should be snatched following the full searching and filtering of recs.
        The returned list is sorted from largest to smallest torrent, in order to optimize FL token usage (if enabled and tokens are available).

        Only returns a list which has a total size of <= self._max_download_allowed_gb. Any remaining torrents are added to the skipped summary list.
        """
        search_elems_by_size = sorted(
            self._search_items_to_snatch, key=lambda si: si._torrent_entry.get_size(unit="MB"), reverse=True
        )
        will_snatch: List[SearchItem] = []
        cumulative_dl_size_gb = 0.0
        for si in search_elems_by_size:
            cur_te_size_gb = si._torrent_entry.get_size("MB")
            if cumulative_dl_size_gb + cur_te_size_gb <= self._max_download_allowed_gb:
                will_snatch.append(si)
                cumulative_dl_size_gb += cur_te_size_gb
            else:
                _LOGGER.debug(
                    f"Skip snatch {si._torrent_entry.get_permalink_url}: would drop ratio below min_allowed_ratio."
                )
                self._add_skipped_snatch_row(si=si, reason=SkippedReason.MIN_RATIO_LIMIT)
        return will_snatch

    def _add_skipped_snatch_row(self, si: SearchItem, reason: SkippedReason) -> None:
        self._skipped_snatch_summary_rows.append(
            [
                si.lfm_rec.rec_type,
                si.lfm_rec.rec_context,
                si.artist_name,
                si.release_name,
                si.track_rec_name,
                str(si._torrent_entry.torrent_id),
                reason.value,
            ]
        )

    def _add_failed_snatch_row(self, si: SearchItem, exc_name: str) -> None:
        snatch_failure_reason = SnatchFailureReason.OTHER
        if exc_name == SnatchFailureReason.RED_API_REQUEST_ERROR or exc_name == SnatchFailureReason.FILE_ERROR:
            snatch_failure_reason = SnatchFailureReason(exc_name)
        self._failed_snatches_summary_rows.append(
            [si._torrent_entry.get_permalink_url(), si.get_matched_mbid(), snatch_failure_reason.value]
        )

    def _add_snatch_success_row(self, si: SearchItem, snatch_path: str, snatched_with_fl: bool) -> None:
        lfm_rec = si._lfm_rec
        te = si._torrent_entry
        self._snatch_summary_rows.append(
            [
                str(lfm_rec.rec_type),
                str(lfm_rec.rec_context),
                str(te.get_artist_name()),
                str(te.get_release_name()),
                str(STATS_TRACK_REC_NONE if not te.get_track_rec_name() else te.get_track_rec_name()),
                str(te.torrent_id),
                str(te.media),
                str("yes" if snatched_with_fl else "no"),
                str(snatch_path),
            ]
        )

    def generate_summary_stats(self) -> None:
        print_and_save_all_searcher_stats(
            skipped_rows=self.skipped_rows,
            failed_snatch_rows=self.failed_snatch_rows,
            snatch_summary_rows=self.snatch_rows,
            output_summary_dir_path=self._output_summary_dir_path,
        )

    @property
    def red_format_preferences(self) -> List[RedFormat]:
        return self._red_format_preferences

    @property
    def max_size_gb(self) -> float:
        return self._max_size_gb

    @property
    def skipped_rows(self) -> List[List[str]]:
        return self._skipped_snatch_summary_rows

    @property
    def failed_snatch_rows(self) -> List[List[str]]:
        return self._failed_snatches_summary_rows

    @property
    def snatch_rows(self) -> List[List[str]]:
        return self._snatch_summary_rows
