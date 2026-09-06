from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from plastered.db.db_models import FailReason, SkipReason, Status
from plastered.db.db_utils import set_result_status
from plastered.models import (
    TRACK_ORIGIN_RELEASE_TYPES,
    RedReleaseType,
    RedUserDetails,
    ReleaseEntry,
    SearchItem,
    SearchStage,
    SearchStepOutcome,
    TorrentEntry,
    TorrentMatch,
    counted,
    origin_label,
    quoted,
    release_group_label,
    release_type_name,
    torrent_label,
)
from plastered.utils.constants import (
    RED_PARAM_CATALOG_NUMBER,
    RED_PARAM_RECORD_LABEL,
    RED_PARAM_RELEASE_TYPE,
    RED_PARAM_RELEASE_YEAR,
)
from plastered.utils.exceptions import MissingTorrentEntryException, SearchItemException, SearchStateException
from plastered.utils.text_utils import EXACT_MATCH_SCORE, MIN_MATCH_SCORE, title_match_score

if TYPE_CHECKING:
    from plastered.config.app_settings import AppSettings, FormatPreference
    from plastered.models import OriginRelease

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


@dataclass(frozen=True)
class ReleaseGroupMatches:
    """
    The outcome of matching one wanted release against an artist's RED release groups
    (`SearchState.match_release_groups`): the candidate groups, best first, plus how the title, release-type and
    year rules treated the artist's groups, which `describe` renders for the search trace.
    """

    wanted_title: str
    wanted_release_type: RedReleaseType | None
    wanted_year: int | None
    entries: list[ReleaseEntry]
    # Groups whose title matched; of those, how many the type / year filters dropped or, in lenient mode, kept despite
    # a different type. Same-titled groups of a type a track cannot originate from are counted separately.
    title_matched: int = 0
    type_dropped: int = 0
    type_mismatched_kept: int = 0
    year_dropped: int = 0
    year_ignored: bool = False
    non_origin_type_ignored: int = 0

    def describe(self) -> str:
        title = quoted(self.wanted_title)
        if self.title_matched == 0:
            if self.non_origin_type_ignored:
                return (
                    f"only {counted(self.non_origin_type_ignored, 'release group')} titled like {title}, none an "
                    "album / EP / single / soundtrack"
                )
            return f"no release group titled like {title}"
        wanted_type = release_type_name(self.wanted_release_type)
        notes: list[str] = []
        if self.type_dropped:
            notes.append(f"{self.type_dropped} dropped for release type (wanted {wanted_type})")
        if self.type_mismatched_kept:
            notes.append(f"{self.type_mismatched_kept} of a different release type (wanted {wanted_type})")
        if self.year_dropped:
            notes.append(f"{self.year_dropped} dropped for year (wanted {self.wanted_year})")
        if self.year_ignored:
            notes.append(f"year filter ({self.wanted_year}) skipped: no title match from that year")
        if self.non_origin_type_ignored:
            notes.append(f"{self.non_origin_type_ignored} more ignored: not an album / EP / single / soundtrack group")
        text = f"{counted(self.title_matched, 'release group')} titled like {title}"
        if notes:
            text += f" ({'; '.join(notes)}); {counted(len(self.entries), 'candidate')} kept"
        return text


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

    def _effective_search_kwarg(
        self, si: SearchItem, search_kwargs: dict[str, Any], red_param: str, enabled_for_scraper: bool
    ) -> Any:
        """
        Returns the optional release attribute to apply during candidate matching, or `None` when unset/disabled.
        Ad-hoc searches use every attribute present (user-supplied or MB-resolved — all such fields are best-effort in
        the ad-hoc flow); scraper items only use those enabled by `red.search`.
        """
        if not (si.is_manual or enabled_for_scraper):
            return None
        return search_kwargs.get(red_param)

    def get_candidate_release_groups(
        self,
        si: SearchItem,
        release_entries: list[ReleaseEntry],
        origin: OriginRelease | None = None,
        strict_release_type: bool = True,
    ) -> list[ReleaseEntry]:
        """
        Matches the wanted release against the artist's RED release groups client-side (RED's search offers no fuzzy
        matching, so titles are matched here rather than via the browse endpoint's exact `groupname` param). The wanted
        release is the item's own (`si.release_name` + `si.get_search_kwargs()`), or — for a track item — the given
        `origin` candidate (its title + `si.get_origin_search_kwargs`). Returns the matching groups ordered best-first:

        1. For a track item (`origin` given), groups of a type a track cannot originate from — anything but an
           album / EP / single / soundtrack (`TRACK_ORIGIN_RELEASE_TYPES`) — are dropped outright, whatever the
           release-type settings: a same-titled compilation or live album carries another version of the track at
           best.
        2. Groups are title-matched via `title_match_score` (with the lenient fuzzy tiers included only when
           `red.search.fuzzy_search_enabled` is on).
        3. When a release type is available, groups of a different type are dropped — or, when not
           `strict_release_type`, merely ranked below the type-matching groups, provided their title matches exactly.
        4. When a release year is available, groups from a different year are dropped — unless that would eliminate
           every remaining candidate, in which case the year filter is skipped entirely: a wrong or edition-specific
           year should narrow the match, never kill it.
        5. Candidates are ordered by title score, then release-type match, then by a matching record label /
           catalogue number. Label and catalogue number are ranking signals only — a mismatch never drops a group.

        The list-only form of `match_release_groups`, which also reports how these rules treated the groups.
        """
        return self.match_release_groups(
            si=si, release_entries=release_entries, origin=origin, strict_release_type=strict_release_type
        ).entries

    def match_release_groups(
        self,
        si: SearchItem,
        release_entries: list[ReleaseEntry],
        origin: OriginRelease | None = None,
        strict_release_type: bool = True,
    ) -> ReleaseGroupMatches:
        """As `get_candidate_release_groups`, also reporting how the title / type / year rules treated the groups."""
        wanted_title = origin.release_name if origin is not None else si.release_name
        search_kwargs = si.get_origin_search_kwargs(origin=origin) if origin is not None else si.get_search_kwargs()
        wanted_release_type = self._effective_search_kwarg(
            si, search_kwargs, RED_PARAM_RELEASE_TYPE, self._use_release_type
        )
        wanted_year = self._effective_search_kwarg(
            si, search_kwargs, RED_PARAM_RELEASE_YEAR, self._use_first_release_year
        )
        wanted_label = self._effective_search_kwarg(si, search_kwargs, RED_PARAM_RECORD_LABEL, self._use_record_label)
        wanted_catalogue_number = self._effective_search_kwarg(
            si, search_kwargs, RED_PARAM_CATALOG_NUMBER, self._use_catalog_number
        )
        scored_entries: list[tuple[float, bool, ReleaseEntry]] = []
        title_matched = non_origin_type_ignored = type_dropped = type_mismatched_kept = 0
        for release_entry in release_entries:
            score = title_match_score(
                wanted_title=wanted_title,
                candidate_title=release_entry.group_name,
                fuzzy_enabled=self._fuzzy_search_enabled,
            )
            if score < MIN_MATCH_SCORE:
                continue
            if origin is not None and release_entry.release_type not in TRACK_ORIGIN_RELEASE_TYPES:
                non_origin_type_ignored += 1
                continue
            title_matched += 1
            release_type_matches = wanted_release_type is None or release_entry.release_type == wanted_release_type
            # A type mismatch drops the group in strict mode; in lenient mode only an exactly-titled group survives
            # it (a word-subset title like "Home Again" for a wanted "Home" plus a wrong type is too weak to snatch on).
            if not release_type_matches and (strict_release_type or score < EXACT_MATCH_SCORE):
                type_dropped += 1
                continue
            if not release_type_matches:
                type_mismatched_kept += 1
            scored_entries.append((score, release_type_matches, release_entry))
        year_dropped = 0
        year_ignored = False
        if wanted_year is not None:
            year_scored_entries = [entry for entry in scored_entries if entry[2].group_year == wanted_year]
            if year_scored_entries:
                year_dropped = len(scored_entries) - len(year_scored_entries)
                scored_entries = year_scored_entries
            elif scored_entries:
                year_ignored = True
                _LOGGER.info(
                    f"Year filter ({wanted_year}) eliminated every candidate group for '{wanted_title}' by "
                    f"'{si.artist_name}'; falling back to the year-agnostic candidates."
                )

        def _rank_key(scored_entry: tuple[float, bool, ReleaseEntry]) -> tuple[float, bool, bool, bool]:
            score, release_type_matches, release_entry = scored_entry
            label_matches = wanted_label is not None and any(
                label.casefold() == wanted_label.casefold() for label in release_entry.record_labels
            )
            catalogue_number_matches = wanted_catalogue_number is not None and any(
                catalogue_number.casefold() == str(wanted_catalogue_number).casefold()
                for catalogue_number in release_entry.catalogue_numbers
            )
            return (score, release_type_matches, label_matches, catalogue_number_matches)

        # `sort` is stable, so equally-ranked groups keep RED's own (release-type + year) listing order.
        scored_entries.sort(key=_rank_key, reverse=True)
        return ReleaseGroupMatches(
            wanted_title=wanted_title,
            wanted_release_type=RedReleaseType(wanted_release_type) if wanted_release_type is not None else None,
            wanted_year=wanted_year,
            entries=[release_entry for _, _, release_entry in scored_entries],
            title_matched=title_matched,
            type_dropped=type_dropped,
            type_mismatched_kept=type_mismatched_kept,
            year_dropped=year_dropped,
            year_ignored=year_ignored,
            non_origin_type_ignored=non_origin_type_ignored,
        )

    def match_album_release(self, si: SearchItem, release_entries: list[ReleaseEntry]) -> TorrentMatch:
        """
        Matches an album item's release against the artist's RED release groups (`match_release_groups`) and ranks
        the candidates' torrents against the format preferences (`select_best_torrent`), tracing the outcome on the
        item.
        """
        matches = self.match_release_groups(si=si, release_entries=release_entries)
        torrent_match = self.select_best_torrent(release_entries=matches.entries)
        si.add_trace_step(
            stage=SearchStage.RED_MATCH,
            outcome=SearchStepOutcome.OK if torrent_match.torrent_entry is not None else SearchStepOutcome.WARNING,
            detail=self._describe_match_attempt(matches=matches, torrent_match=torrent_match),
        )
        return torrent_match

    def _describe_match_attempt(self, matches: ReleaseGroupMatches, torrent_match: TorrentMatch) -> str:
        """The group matching outcome, then how the candidates' torrents fared when there were candidates."""
        text = matches.describe()
        if not matches.entries:
            return text
        return f"{text}; {self._describe_torrent_match(torrent_match=torrent_match)}"

    def _describe_torrent_match(self, torrent_match: TorrentMatch) -> str:
        if (torrent_entry := torrent_match.torrent_entry) is not None:
            text = f"matched {torrent_label(torrent_entry)}"
            if torrent_match.release_entry is not None:
                text += f" in {release_group_label(torrent_match.release_entry)}"
            return text
        if torrent_match.above_max_size_found:
            return f"every torrent matching the format preferences exceeds the size limit ({self._max_size_gb:g} GB)"
        return "no torrent matched the format preferences"

    @staticmethod
    def _trace_origin_attempts(si: SearchItem, attempts: dict[bool, list[str]], matched: bool) -> None:
        """
        Traces a track item's per-candidate matching outcomes (`attempts`: one line per candidate tried, keyed by
        pass — strict release type or not) as one step. A lenient-pass outcome supersedes the strict-pass one for the
        same candidate, so the strict pass is listed only when the lenient pass matched before reaching every
        candidate.
        """
        strict_lines, lenient_lines = attempts[True], attempts[False]
        if not lenient_lines:
            groups = [("Origin candidates tried against RED, best first:", strict_lines)]
        elif matched:
            groups = [
                ("Origin candidates tried against RED, best first (release type as a filter):", strict_lines),
                ("Retried with the release type relaxed to a ranking signal:", lenient_lines),
            ]
        else:
            groups = [
                (
                    "Origin candidates tried against RED, best first (none matched with the release type as a "
                    "filter, so it was relaxed to a ranking signal):",
                    lenient_lines,
                )
            ]
        si.add_trace_step(
            stage=SearchStage.RED_MATCH,
            outcome=SearchStepOutcome.OK if matched else SearchStepOutcome.WARNING,
            detail="\n".join(line for header, lines in groups for line in (header, *lines)),
        )

    def match_track_origin_candidates(self, si: SearchItem, release_entries: list[ReleaseEntry]) -> TorrentMatch:
        """
        Matches a track item's origin candidates against the artist's RED release groups, best candidate first, and
        returns the first torrent match (recording the matching candidate on the item via `set_matched_origin`). A
        strict pass, where each candidate's release type filters the groups as it does for albums, precedes a lenient
        pass where the type only ranks them — a wrong or edition-specific origin release type never eliminates every
        candidate. Both passes only ever consider album / EP / single / soundtrack groups
        (`TRACK_ORIGIN_RELEASE_TYPES`). Candidates the user already snatched are skipped (when `skip_prior_snatches`
        is on). Reports `above_max_size_found` when any candidate's only format matches exceeded the size limit.
        The per-candidate outcomes are traced on the item as one step.
        """
        above_max_size_found = False
        # One line per candidate tried, per pass (see `_trace_origin_attempts`).
        attempts: dict[bool, list[str]] = {True: [], False: []}
        for strict_release_type in (True, False):
            for origin in si.origin_candidates:
                label = origin_label(origin)
                if self._previously_snatched_release(si=si, release_name=origin.release_name):
                    _LOGGER.debug(
                        f"Skipping already-snatched origin candidate '{origin.release_name}' for {si.initial_info}."
                    )
                    attempts[strict_release_type].append(f"• {label}: skipped, already snatched")
                    continue
                matches = self.match_release_groups(
                    si=si, release_entries=release_entries, origin=origin, strict_release_type=strict_release_type
                )
                torrent_match = self.select_best_torrent(release_entries=matches.entries)
                attempts[strict_release_type].append(
                    f"• {label}: {self._describe_match_attempt(matches=matches, torrent_match=torrent_match)}"
                )
                if torrent_match.torrent_entry is not None:
                    _LOGGER.debug(
                        f"Track '{si.track_name}' by '{si.artist_name}' matched via origin release "
                        f"'{origin.release_name}' ({origin.source}; {strict_release_type=})."
                    )
                    si.set_matched_origin(origin=origin)
                    self._trace_origin_attempts(si=si, attempts=attempts, matched=True)
                    return torrent_match
                above_max_size_found = above_max_size_found or torrent_match.above_max_size_found
        self._trace_origin_attempts(si=si, attempts=attempts, matched=False)
        return TorrentMatch(torrent_entry=None, above_max_size_found=above_max_size_found)

    def _previously_snatched_release(self, si: SearchItem, release_name: str) -> bool:
        """Whether `skip_prior_snatches` rules the release out: the user already snatched it (artist + release name)."""
        return (
            self._skip_prior_snatches
            and self._red_user_details is not None
            and self._red_user_details.has_snatched_release(artist=si.artist_name, release=release_name)
        )

    def mb_resolution_would_be_used(self, si: SearchItem) -> bool:
        """
        Whether the MusicBrainz release lookup is worth performing for this item. The ad-hoc flow always resolves it
        (best-effort enrichment of the returned match / optional params). The scraper flow only consults the MB release
        to populate optional RED search fields, so it's needed only when at least one such field is enabled — and not
        when a track's top origin candidate already carries every enabled one of the release type / year from its MB
        recording data (label / catalogue number always need the lookup).
        """
        if si.is_manual:
            return True
        if not self._require_mbid_resolution:
            return False
        top_origin = si.top_origin
        if top_origin is None or self._use_record_label or self._use_catalog_number:
            return True
        # Only a release group's first-release date is a trustworthy origin year: a search-sourced candidate carries
        # just its release's own date, which may be a reissue's.
        needs_release_type = self._use_release_type and top_origin.get_red_release_type() is None
        needs_release_year = self._use_first_release_year and top_origin.first_release_date is None
        return needs_release_type or needs_release_year

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
                        return TorrentMatch(
                            torrent_entry=torrent_entry, above_max_size_found=False, release_entry=release_entry
                        )
                    above_max_size_found = True
        return TorrentMatch(torrent_entry=None, above_max_size_found=above_max_size_found)

    @staticmethod
    def _torrent_matches_format(torrent_entry: TorrentEntry, pref: FormatPreference) -> bool:
        """Whether a torrent's format/encoding/media matches a format preference (ignoring `cd_only_extras`)."""
        te_format = torrent_entry.red_format
        return te_format is not None and (
            te_format.format == pref.format and te_format.encoding == pref.encoding and te_format.media == pref.media
        )
