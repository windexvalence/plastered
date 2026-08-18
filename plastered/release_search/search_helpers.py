from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from plastered.db.db_models import FailReason, SkipReason, Status
from plastered.db.db_utils import set_result_status
from plastered.models import RedUserDetails, ReleaseEntry, SearchItem, TorrentEntry, TorrentMatch
from plastered.release_search.title_matching import MIN_MATCH_SCORE, title_match_score
from plastered.utils.constants import (
    RED_PARAM_CATALOG_NUMBER,
    RED_PARAM_RECORD_LABEL,
    RED_PARAM_RELEASE_TYPE,
    RED_PARAM_RELEASE_YEAR,
)
from plastered.utils.exceptions import MissingTorrentEntryException, SearchItemException, SearchStateException

if TYPE_CHECKING:
    from plastered.config.app_settings import AppSettings, FormatPreference

_LOGGER = logging.getLogger(__name__)


def _required_search_kwargs(use_release_type: bool, use_first_release_year: bool) -> set[str]:
    """
    The search kwargs a scraper item must resolve to proceed. Only the release-type/year fields (the client-side
    *filters*) are ever required — record label and catalogue number are ranking signals, so they are best-effort by
    nature and never gate an item.
    """
    required_kwargs = set()
    if use_release_type:
        required_kwargs.add(RED_PARAM_RELEASE_TYPE)
    if use_first_release_year:
        required_kwargs.add(RED_PARAM_RELEASE_YEAR)
    return required_kwargs


class SearchState:
    """
    Helper class which maintains the variable internal state of the searching process, and
    which handles the pre and post search filtering logic during a search run.
    """

    def __init__(self, app_settings: AppSettings, red_user_details: RedUserDetails | None = None):
        self._skip_prior_snatches = app_settings.red.snatches.skip_prior_snatches
        self._use_release_type = app_settings.red.search.use_release_type
        self._use_first_release_year = app_settings.red.search.use_first_release_year
        self._use_record_label = app_settings.red.search.use_record_label
        self._use_catalog_number = app_settings.red.search.use_catalog_number
        self._fuzzy_search_enabled = app_settings.red.search.fuzzy_search_enabled
        self._required_red_search_kwargs: set[str] = _required_search_kwargs(
            use_release_type=self._use_release_type, use_first_release_year=self._use_first_release_year
        )
        # MBID resolution is used when at least one optional search field is enabled: release type and year act as
        # client-side candidate filters, record label and catalogue number act as ranking signals.
        self._require_mbid_resolution = (
            self._use_release_type or self._use_first_release_year or self._use_record_label or self._use_catalog_number
        )
        self._red_format_preferences = app_settings.get_red_format_preferences()
        self._max_size_gb = app_settings.red.snatches.max_size_gb
        self._min_allowed_ratio = app_settings.red.snatches.min_allowed_ratio
        self._max_download_allowed_gb = 0.0
        self._red_user_details: RedUserDetails | None = None
        # Route through the setter so `_max_download_allowed_gb` is computed for BOTH initialization paths: a state
        # constructed with already-fetched details (a reused `ReleaseSearcher`) and one populated later via
        # `set_red_user_details` (the first run). Leaving the cap at 0.0 here would skip every snatch as MIN_RATIO_LIMIT.
        if red_user_details is not None:
            self.set_red_user_details(red_user_details=red_user_details)
        self._tids_to_snatch: set[int] = set()
        self._search_items_to_snatch: list[SearchItem] = []
        self._manual_search_item_to_snatch: SearchItem | None = None
        # In-memory, run-scoped cache of RED artist release-group listings: multiple recs in a scraper run often
        # share an artist, and the artist endpoint returns the artist's *entire* listing, so one fetch serves them
        # all. Never persisted — a fresh `SearchState` (one per run) always starts empty.
        self._artist_release_groups_cache: dict[str, list[ReleaseEntry]] = {}

    def get_cached_artist_release_groups(self, artist_name: str) -> list[ReleaseEntry] | None:
        """
        Returns this run's cached RED release-group listing for the artist, or `None` when the artist has not been
        fetched yet this run. Keyed case-insensitively, matching RED's own artist-name lookup behavior.
        """
        return self._artist_release_groups_cache.get(artist_name.casefold())

    def cache_artist_release_groups(self, artist_name: str, release_entries: list[ReleaseEntry]) -> None:
        """
        Caches an artist's fetched RED release-group listing (in memory only) for the remainder of the run. An empty
        listing is cached too: an artist RED doesn't know stays unknown for the whole run.
        """
        self._artist_release_groups_cache[artist_name.casefold()] = release_entries

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

    def _effective_search_kwarg(self, si: SearchItem, red_param: str, enabled_for_scraper: bool) -> Any:
        """
        Returns the optional release attribute to apply during candidate matching, or `None` when unset/disabled.
        Ad-hoc searches use every attribute present on the item (user-supplied or MB-resolved — all such fields are
        best-effort in the ad-hoc flow); scraper items only use those enabled by `red.search`.
        """
        if not (si.is_manual or enabled_for_scraper):
            return None
        return si.get_search_kwargs().get(red_param)

    def get_candidate_release_groups(self, si: SearchItem, release_entries: list[ReleaseEntry]) -> list[ReleaseEntry]:
        """
        Matches the wanted release against the artist's RED release groups client-side (RED's search offers no fuzzy
        matching, so titles are matched here rather than via the browse endpoint's exact `groupname` param). Returns
        the matching groups ordered best-first:

        1. Groups are title-matched via `title_match_score` (with the lenient fuzzy tiers included only when
           `red.search.fuzzy_search_enabled` is on).
        2. When a release type is available, groups of a different type are dropped.
        3. When a release year is available, groups from a different year are dropped — unless that would eliminate
           every remaining candidate, in which case the year filter is skipped entirely: a wrong or edition-specific
           year should narrow the match, never kill it.
        4. Candidates are ordered by title score, then by a matching record label / catalogue number. These two are
           ranking signals only — a mismatch never drops a group.
        """
        wanted_release_type = self._effective_search_kwarg(si, RED_PARAM_RELEASE_TYPE, self._use_release_type)
        wanted_year = self._effective_search_kwarg(si, RED_PARAM_RELEASE_YEAR, self._use_first_release_year)
        wanted_label = self._effective_search_kwarg(si, RED_PARAM_RECORD_LABEL, self._use_record_label)
        wanted_catalogue_number = self._effective_search_kwarg(si, RED_PARAM_CATALOG_NUMBER, self._use_catalog_number)
        scored_entries: list[tuple[float, ReleaseEntry]] = []
        for release_entry in release_entries:
            score = title_match_score(
                wanted_title=si.release_name,
                candidate_title=release_entry.group_name,
                fuzzy_enabled=self._fuzzy_search_enabled,
            )
            if score < MIN_MATCH_SCORE:
                continue
            if wanted_release_type is not None and release_entry.release_type != wanted_release_type:
                continue
            scored_entries.append((score, release_entry))
        if wanted_year is not None:
            year_scored_entries = [(score, re) for score, re in scored_entries if re.group_year == wanted_year]
            if year_scored_entries:
                scored_entries = year_scored_entries
            elif scored_entries:
                _LOGGER.info(
                    f"Year filter ({wanted_year}) eliminated every candidate group for '{si.release_name}' by "
                    f"'{si.artist_name}'; falling back to the year-agnostic candidates."
                )

        def _rank_key(scored_entry: tuple[float, ReleaseEntry]) -> tuple[float, bool, bool]:
            score, release_entry = scored_entry
            label_matches = wanted_label is not None and any(
                label.casefold() == wanted_label.casefold() for label in release_entry.record_labels
            )
            catalogue_number_matches = wanted_catalogue_number is not None and any(
                catalogue_number.casefold() == str(wanted_catalogue_number).casefold()
                for catalogue_number in release_entry.catalogue_numbers
            )
            return (score, label_matches, catalogue_number_matches)

        # `sort` is stable, so equally-ranked groups keep RED's own (release-type + year) listing order.
        scored_entries.sort(key=_rank_key, reverse=True)
        return [release_entry for _, release_entry in scored_entries]

    def mb_resolution_would_be_used(self, si: SearchItem) -> bool:
        """
        Whether the MusicBrainz release lookup is worth performing for this item. The scraper flow only consults the MB
        release to populate optional RED search fields, so it's needed only when at least one such field is enabled. The
        ad-hoc flow always resolves it (best-effort enrichment of the returned match / optional params).
        """
        return si.is_manual or self._require_mbid_resolution

    def _pre_mbid_reso_rule_not_previously_snatched(self, si: SearchItem) -> SkipReason | None:
        """Return `True` if si has already been snatched, return `False` otherwise."""
        if not self._red_user_details:
            msg = "Red User Details not initialized."
            _LOGGER.error(msg)
            raise SearchStateException(msg)
        # Use `si.release_name`, not `initial_info.get_human_readable_entity_str()`: for a track the latter is the track
        # name, whereas the prior-snatch dict is keyed by release name. `release_name` is the album name for albums and
        # the resolved origin-release name for tracks (this filter runs after track resolution in the chain).
        if self._skip_prior_snatches and self._red_user_details.has_snatched_release(
            artist=si.artist_name, release=si.release_name
        ):
            return SkipReason.ALREADY_SNATCHED
        return None

    def post_mbid_reso_rule_has_required_fields(self, si: SearchItem) -> SkipReason | None:
        """
        Return `SkipReason.UNRESOLVED_REQUIRED_SEARCH_FIELDS` if the SearchItem should be skipped due to missing
        fields which are marked as required by the current user-specified app config settings.
        """
        # In the ad-hoc flow every optional search field is best-effort: a missing field never drops the item.
        if si.is_manual:
            return None
        if not self._require_mbid_resolution:
            return None
        if not si.search_kwargs_has_all_required_fields(required_kwargs=self._required_red_search_kwargs):
            # Attribute the missing fields to an upstream API request failure when one occurred (checking LFM first
            # since it resolves earlier in the chain and gates the MB lookup): without the failure the fields might
            # have resolved, so the recorded reason should surface the failed request, not a generic unresolved skip.
            if si.lfm_request_failed:
                return SkipReason.LFM_REQUEST_FAILURE
            if si.mb_request_failed:
                return SkipReason.MB_REQUEST_FAILURE
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

    def add_search_item_to_snatch(self, si: SearchItem) -> None:
        if not si.torrent_entry:  # pragma: no cover
            raise MissingTorrentEntryException("SearchItem missing torrent entry")
        if si.is_manual:
            self._manual_search_item_to_snatch = si
        else:
            self._search_items_to_snatch.append(si)
            self._tids_to_snatch.add(si.torrent_entry.torrent_id)

    def record_matched_result_row(self) -> None:
        """
        For an ad-hoc search-only run (i.e. snatching disabled / not requested): record the RED match that was found,
        if any, as a `MATCHED` result row so the matched release can be returned to the client. A no-op when no match
        was found (the post-RED-search filter has already written the appropriate SKIPPED row in that case).
        """
        if (si := self._manual_search_item_to_snatch) is not None:
            self._record_matched_row(si=si)

    def record_matched_result_rows(self) -> None:
        """
        For a scraper run with downloads disabled: record every RED match found this run as a `MATCHED` result row, so
        the matches can be reviewed and selectively downloaded later from the run-history page. No ratio/size cap is
        applied here — the per-torrent `max_size_gb` cap was already applied during matching, and the cumulative
        ratio-based cap only governs automatic snatching, not the user's explicit retroactive selection.
        """
        for si in self._search_items_to_snatch:
            self._record_matched_row(si=si)

    def _record_matched_row(self, si: SearchItem) -> None:
        """Writes the `MATCHED` status row for a single matched `SearchItem`."""
        te = si.torrent_entry
        if te is None:
            return
        set_result_status(
            search_id=si.search_id,
            status=Status.MATCHED,
            status_model_kwargs={
                "tid": te.torrent_id,
                "red_permalink": te.get_permalink_url(),
                "matched_mbid": si.get_matched_mbid(),
                "size_gb": te.get_size(unit="GB"),
                "media": te.media,
                "format": te.format,
                "encoding": te.encoding,
            },
        )

    def get_search_items_to_snatch(self, manual_run: bool = False) -> list[SearchItem]:
        """
        Called by the ReleaseSearcher, returns the list of SearchItems which should be snatched following the full searching and filtering of recs.

        For a `manual_run` (single ad-hoc search) the matched item is returned as-is: it is an explicit, user-initiated
        download, so only the per-torrent `max_size_gb` cap (applied during matching) governs it — the ratio-based
        cumulative cap below does NOT apply.

        For the scraper flow the list is sorted from largest to smallest torrent (to optimize FL token usage if enabled)
        and is capped so its cumulative size is <= self._max_download_allowed_gb; any torrents that would exceed that
        ratio-based limit are dropped and recorded as skipped.
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

    def select_best_torrent(self, release_entries: list[ReleaseEntry]) -> TorrentMatch:
        """
        Ranks the torrents of the candidate release groups (best-candidate-first, see
        `get_candidate_release_groups`) against the configured format preferences, client-side. The highest-priority
        preference that has a size-acceptable matching torrent wins; among matches for a preference, groups are
        visited in candidate-rank order (each group's torrents are seeder-ordered, see
        `ReleaseEntry.from_artist_torrent_group_json_blob`) and the first torrent within `max_size_gb` is chosen.

        `above_max_size_found` is reported when a format-matching torrent existed but every candidate exceeded the size
        limit. Matching is by format/encoding/media only (log/cue `cd_only_extras` are intentionally ignored).
        """
        above_max_size_found = False
        for pref in self._red_format_preferences:
            for release_entry in release_entries:
                for torrent_entry in release_entry.get_torrent_entries():
                    if not self._torrent_matches_format(torrent_entry=torrent_entry, pref=pref):
                        continue
                    if torrent_entry.get_size(unit="GB") <= self._max_size_gb:
                        return TorrentMatch(torrent_entry=torrent_entry, above_max_size_found=False)
                    above_max_size_found = True
        return TorrentMatch(torrent_entry=None, above_max_size_found=above_max_size_found)

    @staticmethod
    def _torrent_matches_format(torrent_entry: TorrentEntry, pref: FormatPreference) -> bool:
        """Whether a torrent's format/encoding/media matches a format preference (ignoring `cd_only_extras`)."""
        te_format = torrent_entry.red_format
        return te_format is not None and (
            te_format.format == pref.format and te_format.encoding == pref.encoding and te_format.media == pref.media
        )
