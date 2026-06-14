import logging
from urllib.parse import quote_plus

from plastered.config.app_settings import AppSettings, FormatPreference
from plastered.db.db_models import FailReason, SkipReason, Status
from plastered.db.db_utils import set_result_status
from plastered.models import RecContext, RedFormat, RedUserDetails, SearchItem, TorrentEntry
from plastered.utils.constants import (
    OPTIONAL_RED_PARAMS,
    RED_PARAM_CATALOG_NUMBER,
    RED_PARAM_RECORD_LABEL,
    RED_PARAM_RELEASE_TYPE,
    RED_PARAM_RELEASE_YEAR,
)
from plastered.utils.exceptions import MissingTorrentEntryException, SearchItemException, SearchStateException

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


class SearchState:
    """
    Helper class which maintains the variable internal state of the searching process, and
    which handles the pre and post search filtering logic during a search run.
    """

    def __init__(self, app_settings: AppSettings, red_user_details: RedUserDetails | None = None):
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
        self._max_download_allowed_gb = 0.0
        self._red_user_details = red_user_details
        self._run_download_total_gb = 0.0
        self._tids_to_snatch: set[int] = set()
        self._search_items_to_snatch: list[SearchItem] = []
        self._manual_search_item_to_snatch: SearchItem | None = None

    def red_user_details_is_initialized(self) -> bool:
        """Returns `True` if the red user details have been initialized, `False` otherwise."""
        return self._red_user_details is not None

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
        artist_name = si.initial_info.encoded_artist_str
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

    def _pre_mbid_reso_rule_not_previously_snatched(self, si: SearchItem) -> SkipReason | None:
        """Return `True` if si has already been snatched, return `False` otherwise."""
        if not self._red_user_details:
            msg = "Red User Details not initialized."
            _LOGGER.error(msg)
            raise SearchStateException(msg)
        if self._skip_prior_snatches and self._red_user_details.has_snatched_release(
            artist=si.artist_name, release=si.initial_info.get_human_readable_entity_str()
        ):
            return SkipReason.ALREADY_SNATCHED
        return None

    def _pre_mbid_reso_rule_allowed_rec_context(self, si: SearchItem) -> SkipReason | None:
        """
        Return `True` if si has an `IN_LIBRARY` context and self._allow_library items is `False`, return `False` otherwise.
        """
        if not self._allow_library_items and si.initial_info.rec_context == RecContext.IN_LIBRARY:
            return SkipReason.REC_CONTEXT_FILTERING
        return None

    def post_mbid_reso_rule_has_required_fields(self, si: SearchItem) -> SkipReason | None:
        """
        Return `SkipReason.UNRESOLVED_REQUIRED_SEARCH_FIELDS` if the SearchItem should be skipped due to missing
        fields which are marked as required by the current user-specified app config settings.
        """
        if not self._require_mbid_resolution:
            return None
        if not si.search_kwargs_has_all_required_fields(required_kwargs=self._required_red_search_kwargs):
            return SkipReason.UNRESOLVED_REQUIRED_SEARCH_FIELDS
        return None

    def _post_red_search_rule_not_dupe_snatch(self, si: SearchItem) -> SkipReason | None:
        """
        Return `True` if si corresponds to an already to-be-snatched entry or to a past snatch.
        """
        if not self._red_user_details:
            raise SearchStateException("Red user details not initialized")
        if not si.torrent_entry:
            raise SearchItemException("SearchItem instance has not torrent_entry.")
        # Ignore this condition for manual searches since those are not done in batch
        if (not si.is_manual) and si.torrent_entry.torrent_id in self._tids_to_snatch:
            return SkipReason.DUPE_OF_ANOTHER_REC
        if self._red_user_details.has_snatched_tid(tid=si.torrent_entry.torrent_id):
            return SkipReason.ALREADY_SNATCHED
        return None

    def post_red_search_rule_found_match_with_allowed_size(self, si: SearchItem) -> SkipReason | None:
        if not si.found_red_match():
            _LOGGER.info(
                f"No valid RED match found for {si.initial_info.entity_type}: '{si.initial_info.get_human_readable_entity_str()}' by '{si.artist_name}'"
            )
            return SkipReason.ABOVE_MAX_ALLOWED_SIZE if si.above_max_size_te_found else SkipReason.NO_MATCH_FOUND
        return None

    def add_snatch_final_status_row(
        self, si: SearchItem, snatched_with_fl: bool, snatch_path: str, exc_name: str | None
    ) -> None:
        """
        Called for any torrent once it has either been successfully snatched, or a failure during the snatch attempt took place.
        """
        if exc_name:
            self._add_failed_snatch_row(si=si, exc_name=exc_name)
            return
        if not si.torrent_entry:  # pragma: no cover
            raise MissingTorrentEntryException("SearchItem missing torrent entry")
        self._add_grabbed_row(si=si, snatch_path=snatch_path, snatched_with_fl=snatched_with_fl)
        if te := si.torrent_entry:
            self._update_run_dl_total(te=te)

    def _update_run_dl_total(self, te: TorrentEntry) -> None:  # pragma: no cover
        self._run_download_total_gb += te.get_size(unit="GB")

    def add_search_item_to_snatch(self, si: SearchItem) -> None:
        if not si.torrent_entry:  # pragma: no cover
            raise MissingTorrentEntryException("SearchItem missing torrent entry")
        if si.is_manual:
            self._manual_search_item_to_snatch = si  # pragma: no cover
        else:
            self._search_items_to_snatch.append(si)
            self._tids_to_snatch.add(si.torrent_entry.torrent_id)

    def get_search_items_to_snatch(self, manual_run: bool = False) -> list[SearchItem]:
        """
        Called by the ReleaseSearcher, returns the list of SearchItems which should be snatched following the full searching and filtering of recs.
        The returned list is sorted from largest to smallest torrent, in order to optimize FL token usage (if enabled and tokens are available).

        Only returns a list which has a total size of <= self._max_download_allowed_gb. Any remaining torrents are added to the skipped summary list.
        """
        if manual_run and self._manual_search_item_to_snatch is not None:
            return [self._manual_search_item_to_snatch]
        elif manual_run:
            return []
        search_elems_by_size = sorted(
            self._search_items_to_snatch,
            key=lambda si: si.torrent_entry.get_size(unit="MB"),  # type: ignore [union-attr]
            reverse=True,  # type: ignore
        )
        will_snatch: list[SearchItem] = []
        cumulative_dl_size_gb = 0.0
        for si in search_elems_by_size:
            valid_te_size = self._te_size_acceptable(cumulative_dl_size_gb=cumulative_dl_size_gb, si=si)
            if valid_te_size >= 0:  # pragma: no cover
                cumulative_dl_size_gb += valid_te_size
                will_snatch.append(si)
        return will_snatch

    def _te_size_acceptable(self, cumulative_dl_size_gb: float, si: SearchItem) -> float:
        """
        Returns `si.torrent_entry` size in GB when the provided `te` size will not cause `cumulative_dl_size_gb` to
        exceed `self._max_download_allowed_gb`. Otherwise, returns a negative number.
        """
        if not (te := si.torrent_entry):  # pragma: no cover
            raise MissingTorrentEntryException("Missing torrent_entry")
        te_size_gb = te.get_size("GB")
        if cumulative_dl_size_gb + te_size_gb <= self._max_download_allowed_gb:
            return te_size_gb
        _LOGGER.info(f"Skip snatch {te.get_permalink_url}: would drop ratio below min_allowed_ratio.")
        self._add_skipped_snatch_row(si=si, reason=SkipReason.MIN_RATIO_LIMIT)
        return -1.0

    def _add_skipped_snatch_row(self, si: SearchItem, reason: SkipReason) -> None:  # pragma: no cover
        _LOGGER.debug(
            f"Refreshing result record for search state artist='{si.artist_name}' entity_name='{si.initial_info.get_human_readable_entity_str()}' ..."
        )
        set_result_status(search_id=si.search_id, status=Status.SKIPPED, status_model_kwargs={"skip_reason": reason})

    def _add_failed_snatch_row(self, si: SearchItem, exc_name: str) -> None:  # pragma: no cover
        snatch_failure_reason = FailReason.OTHER
        if exc_name == FailReason.RED_API_REQUEST_ERROR or exc_name == FailReason.FILE_ERROR:  # pragma: no cover
            snatch_failure_reason = FailReason(exc_name)
        set_result_status(
            search_id=si.search_id,
            status=Status.FAILED,
            status_model_kwargs={
                "red_permalink": si.torrent_entry.get_permalink_url() if si.torrent_entry else None,
                "matched_mbid": si.get_matched_mbid(),
                "fail_reason": snatch_failure_reason,
            },
        )

    def _add_grabbed_row(self, si: SearchItem, snatch_path: str, snatched_with_fl: bool) -> None:  # pragma: no cover
        if not (te := si.torrent_entry):  # pragma: no cover
            raise MissingTorrentEntryException("Missing expected torrent_entry field.")
        set_result_status(
            search_id=si.search_id,
            status=Status.GRABBED,
            status_model_kwargs={"fl_token_used": snatched_with_fl, "snatch_path": snatch_path, "tid": te.torrent_id},
        )

    @property
    def red_format_preferences(self) -> list[FormatPreference]:  # pragma: no cover
        return self._red_format_preferences

    @property
    def max_size_gb(self) -> float:  # pragma: no cover
        return self._max_size_gb
