import logging
from urllib.parse import quote_plus

from plastered.config.app_settings import AppSettings
from plastered.models.red_models import RedFormat, RedUserDetails, TorrentEntry
from plastered.models.search_item import SearchItem
from plastered.models.types import RecContext
from plastered.stats.stats import SkippedReason, SnatchFailureReason, print_and_save_all_searcher_stats
from plastered.utils.constants import (
    OPTIONAL_RED_PARAMS,
    RED_PARAM_CATALOG_NUMBER,
    RED_PARAM_RECORD_LABEL,
    RED_PARAM_RELEASE_TYPE,
    RED_PARAM_RELEASE_YEAR,
    STATS_NONE,
    STATS_TRACK_REC_NONE,
)

_LOGGER = logging.getLogger(__name__)


def _require_mbid_resolution(
    use_release_type: bool, use_first_release_year: bool, use_record_label: bool, use_catalog_number: bool
) -> bool:
    return use_release_type or use_first_release_year or use_record_label or use_catalog_number


def _required_search_kwargs(
    use_release_type: bool, use_first_release_year: bool, use_record_label: bool, use_catalog_number: bool
) -> set[str]:
    required_kwargs = set()
    if use_release_type:
        required_kwargs.add(RED_PARAM_RELEASE_TYPE)
    if use_first_release_year:
        required_kwargs.add(RED_PARAM_RELEASE_YEAR)
    if use_record_label:
        required_kwargs.add(RED_PARAM_RECORD_LABEL)
    if use_catalog_number:
        required_kwargs.add(RED_PARAM_CATALOG_NUMBER)
    return required_kwargs


# TODO (later): break out SearchItem definition into separate file
class SearchState:
    """
    Helper class which maintains the variable internal state of the searchingm process, and
    which handles the pre and post search filtering logic during a search run.
    """

    def __init__(self, app_settings: AppSettings):
        self._skip_prior_snatches = app_settings.red.snatches.skip_prior_snatches
        self._allow_library_items = app_settings.lfm.allow_library_items
        self._use_release_type = app_settings.red.search.use_release_type
        self._use_first_release_year = app_settings.red.search.use_first_release_year
        self._use_record_label = app_settings.red.search.use_record_label
        self._use_catalog_number = app_settings.red.search.use_catalog_number
        self._require_mbid_resolution = _require_mbid_resolution(
            use_release_type=self._use_release_type,
            use_first_release_year=self._use_first_release_year,
            use_record_label=self._use_record_label,
            use_catalog_number=self._use_catalog_number,
        )
        self._required_red_search_kwargs: set[str] = _required_search_kwargs(
            use_release_type=self._use_release_type,
            use_first_release_year=self._use_first_release_year,
            use_record_label=self._use_record_label,
            use_catalog_number=self._use_catalog_number,
        )
        self._red_format_preferences = app_settings.get_red_format_preferences()
        self._max_size_gb = app_settings.red.snatches.max_size_gb
        self._min_allowed_ratio = app_settings.red.snatches.min_allowed_ratio
        self._output_summary_dir_path = app_settings.get_output_summary_dir_path()
        self._max_download_allowed_gb = 0.0
        self._red_user_details: RedUserDetails | None = None
        self._run_download_total_gb = 0.0
        self._snatch_summary_rows: list[list[str]] = []
        self._skipped_snatch_summary_rows: list[list[str]] = []
        self._failed_snatches_summary_rows: list[list[str]] = []
        self._tids_to_snatch: set[int] = set()
        self._search_items_to_snatch: list[SearchItem] = []

    def set_red_user_details(self, red_user_details: RedUserDetails) -> None:
        """
        Updates the relevant information related to the RedUserDetails instance provided.
        """
        self._max_download_allowed_gb = red_user_details.calculate_max_download_allowed_gb(
            min_allowed_ratio=self._min_allowed_ratio
        )
        self._red_user_details = red_user_details

    # pylint: disable=redefined-builtin
    def create_red_browse_params(self, red_format: RedFormat, si: SearchItem) -> str:
        """Utility method for creating the RED browse API params string"""
        artist_name = si.lfm_rec.artist_str
        album_name = quote_plus(si.release_name)
        format = red_format.get_format()
        encoding = red_format.get_encoding()
        media = red_format.get_media()
        # TODO: figure out why the `order_by` param appears to be ignored whenever the params also have `group_results=1`.
        browse_request_params = f"artistname={artist_name}&groupname={album_name}&format={format}&encoding={encoding}&media={media}&group_results=1&order_by=seeders&order_way=desc"
        for red_param in OPTIONAL_RED_PARAMS:
            if red_param in self._required_red_search_kwargs:  # noqa: SIM102
                if red_param_val := si.get_search_kwargs().get(red_param):
                    browse_request_params += f"&{red_param}={red_param_val}"
        return browse_request_params

    def post_resolve_track_filter(self, si: SearchItem) -> bool:
        """
        Return True if the track-rec-based SearchItem is valid to search for on the various APIs.
        Return False otherwise if the SearchItem should be skipped given the lack of resolved origin release.
        """
        if not si.lfm_track_info:
            _LOGGER.warning(f"Unable to find origin release for track rec: '{si.track_name}' by '{si.artist_name}'")
            self._add_skipped_snatch_row(si=si, reason=SkippedReason.NO_SOURCE_RELEASE_FOUND)
            return False
        return True

    def _pre_search_rule_skip_prior_snatch(self, si: SearchItem) -> bool:
        """Return `True` if si has already been snatched, return `False` otherwise."""
        return self._skip_prior_snatches and self._red_user_details.has_snatched_release(
            artist=si.artist_name, release=si.lfm_rec.get_human_readable_entity_str()
        )

    def _pre_search_rule_skip_library_items(self, si: SearchItem) -> bool:
        """
        Return `True` if si has an `IN_LIBRARY` context and self._allow_library items is `False`, return `False` otherwise.
        """
        return not self._allow_library_items and si.lfm_rec.rec_context == RecContext.IN_LIBRARY

    def pre_mbid_resolution_filter(self, si: SearchItem) -> bool:
        """
        Return `True` if the SearchItem is valid to continue searching for on the various
        field resolution APIs (mb / LFM), or False if the SearchItem should be skipped given
        the current user-specified app config settings.
        """
        artist = si.artist_name
        release = si.release_name
        if self._pre_search_rule_skip_prior_snatch(si=si):
            _LOGGER.debug("'skip_prior_snatches' config field is set to True")
            _LOGGER.debug(f"'{release}' by '{artist}' due to prior snatch found in release group")
            self._add_skipped_snatch_row(si=si, reason=SkippedReason.ALREADY_SNATCHED)
            return False
        if self._pre_search_rule_skip_library_items(si=si):
            _LOGGER.debug(f"'allow_library_items' config field is set to {self._allow_library_items}.")
            _LOGGER.debug(f"Skipped '{release}' by '{artist}'. Rec context is {RecContext.IN_LIBRARY.value}")
            self._add_skipped_snatch_row(si=si, reason=SkippedReason.REC_CONTEXT_FILTERING)
            return False
        return True

    def post_mbid_resolution_filter(self, si: SearchItem) -> bool:
        """
        Return `True` if the SearchItem is valid to continue searching for on RED after having attempted to
        resolve the additional fields for building the RED browse query params.
        Return `False` if the SearchItem should be skipped due to missing fields which are marked as required
        by the current user-specified app config settings.
        """
        if not self._require_mbid_resolution:
            return True
        if not si.search_kwargs_has_all_required_fields(required_kwargs=self._required_red_search_kwargs):
            self._add_skipped_snatch_row(si=si, reason=SkippedReason.UNRESOLVED_REQUIRED_SEARCH_FIELDS)
            return False
        return True

    def _post_search_rule_skip_already_scheduled_snatch(self, si: SearchItem) -> bool:
        """
        Return `True` if si corresponds to an already to-be-snatched entry and should be skipped. `False` otherwise.
        """
        return si.torrent_entry.torrent_id in self._tids_to_snatch

    def _post_search_rule_dupe_snatch(self, si: SearchItem) -> bool:
        """
        Return `True` if si corresponds to an already to-be-snatched entry or to a past snatch.
        """
        if si.torrent_entry.torrent_id in self._tids_to_snatch:
            self._add_skipped_snatch_row(si=si, reason=SkippedReason.DUPE_OF_ANOTHER_REC)
            return True
        if self._red_user_details.has_snatched_tid(tid=si.torrent_entry.torrent_id):
            self._add_skipped_snatch_row(si=si, reason=SkippedReason.ALREADY_SNATCHED)
            return True
        return False

    def post_red_search_filter(self, si: SearchItem) -> bool:
        """
        Return `True` if the provided SearchItem and associated matched_te is valid to add to the
        pending list of torrents to snatch, otherwise update the skipped_snatch_rows accordingly and return False.
        """
        # No match found
        if not si.found_red_match():
            _LOGGER.info(
                f"No valid RED match found for {si.lfm_rec.rec_type}: '{si.lfm_rec.get_human_readable_entity_str()}' by '{si.artist_name}'"
            )
            skip_reason = SkippedReason.ABOVE_MAX_SIZE if si.above_max_size_te_found else SkippedReason.NO_MATCH_FOUND
            self._add_skipped_snatch_row(si=si, reason=skip_reason)
            return False
        # Check whether the match is tied to a release which is already pending snatching during this run
        if self._post_search_rule_dupe_snatch(si=si):  # noqa: SIM103
            return False
        return True

    def add_snatch_final_status_row(
        self, si: SearchItem, snatched_with_fl: bool, snatch_path: str | None, exc_name: str | None
    ) -> None:
        """
        Called for any torrent once it has either been successfully snatched, or a failure during the snatch attempt took place.
        """
        if exc_name:
            self._add_failed_snatch_row(si=si, exc_name=exc_name)
            return
        self._add_snatch_success_row(si=si, snatch_path=snatch_path, snatched_with_fl=snatched_with_fl)
        self._update_run_dl_total(te=si.torrent_entry)

    def _update_run_dl_total(self, te: TorrentEntry) -> None:
        self._run_download_total_gb += te.get_size(unit="GB")

    def add_search_item_to_snatch(self, si: SearchItem) -> None:
        self._search_items_to_snatch.append(si)
        self._tids_to_snatch.add(si.torrent_entry.torrent_id)

    def requires_mbid_resolution(self) -> bool:  # pragma: no cover
        return self._require_mbid_resolution

    def get_search_items_to_snatch(self) -> list[SearchItem]:
        """
        Called by the ReleaseSearcher, returns the list of SearchItems which should be snatched following the full searching and filtering of recs.
        The returned list is sorted from largest to smallest torrent, in order to optimize FL token usage (if enabled and tokens are available).

        Only returns a list which has a total size of <= self._max_download_allowed_gb. Any remaining torrents are added to the skipped summary list.
        """
        search_elems_by_size = sorted(
            self._search_items_to_snatch, key=lambda si: si.torrent_entry.get_size(unit="MB"), reverse=True
        )
        will_snatch: list[SearchItem] = []
        cumulative_dl_size_gb = 0.0
        for si in search_elems_by_size:
            cur_te_size_gb = si.torrent_entry.get_size("GB")
            if cumulative_dl_size_gb + cur_te_size_gb <= self._max_download_allowed_gb:
                will_snatch.append(si)
                cumulative_dl_size_gb += cur_te_size_gb
            else:
                _LOGGER.info(
                    f"Skip snatch {si.torrent_entry.get_permalink_url}: would drop ratio below min_allowed_ratio."
                )
                self._add_skipped_snatch_row(si=si, reason=SkippedReason.MIN_RATIO_LIMIT)
        return will_snatch

    def _add_skipped_snatch_row(self, si: SearchItem, reason: SkippedReason) -> None:
        self._skipped_snatch_summary_rows.append(
            [
                str(si.lfm_rec.rec_type),
                str(si.lfm_rec.rec_context),
                str(si.artist_name),
                str(si.release_name),
                str(si.track_rec_name),
                str(si.torrent_entry.torrent_id) if si.torrent_entry else STATS_NONE,
                reason.value,
            ]
        )

    def _add_failed_snatch_row(self, si: SearchItem, exc_name: str) -> None:
        snatch_failure_reason = SnatchFailureReason.OTHER
        if exc_name == SnatchFailureReason.RED_API_REQUEST_ERROR or exc_name == SnatchFailureReason.FILE_ERROR:
            snatch_failure_reason = SnatchFailureReason(exc_name)
        self._failed_snatches_summary_rows.append(
            [si.torrent_entry.get_permalink_url(), si.get_matched_mbid(), snatch_failure_reason.value]
        )

    def _add_snatch_success_row(self, si: SearchItem, snatch_path: str, snatched_with_fl: bool) -> None:
        lfm_rec = si.lfm_rec
        te = si.torrent_entry
        self._snatch_summary_rows.append(
            [
                str(lfm_rec.rec_type),
                str(lfm_rec.rec_context),
                str(si.artist_name),
                str(si.release_name),
                str(STATS_TRACK_REC_NONE if not te.track_rec_name else te.track_rec_name),
                str(te.torrent_id),
                str(te.media),
                str("yes" if snatched_with_fl else "no"),
                str(snatch_path),
            ]
        )

    def generate_summary_stats(self) -> None:
        print_and_save_all_searcher_stats(
            skipped_rows=self._skipped_snatch_summary_rows,
            failed_snatch_rows=self._failed_snatches_summary_rows,
            snatch_summary_rows=self._snatch_summary_rows,
            output_summary_dir_path=self._output_summary_dir_path,
        )

    @property
    def red_format_preferences(self) -> list[RedFormat]:
        return self._red_format_preferences

    @property
    def max_size_gb(self) -> float:
        return self._max_size_gb
