from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from plastered.models.adhoc_search_models import AdhocSearch
from plastered.models.lfm_models import LFMAlbumInfo, LFMRec
from plastered.models.search_trace import TraceStep
from plastered.models.types import EntityType
from plastered.utils.constants import RED_PARAM_RELEASE_TYPE, RED_PARAM_RELEASE_YEAR

if TYPE_CHECKING:
    from plastered.models.musicbrainz_models import MBRelease
    from plastered.models.origin_release import OriginRelease
    from plastered.models.red_models import TorrentEntry, TorrentMatch
    from plastered.models.search_trace import SearchStage, SearchStepOutcome

type InitialInfo = LFMRec | AdhocSearch


# TODO [later]: Consolidate the `SearchRecord` db model and `SearchItem` into a single class.
@dataclass
class SearchItem:
    """
    Class which represents the full range of possible information that may be associated with an LFMRec over the
    duration of a search run. Ultimately, this is the individual object which most of the search functionality will work with
    and/or update during the search and filtering resolution of a given rec.
    """

    initial_info: InitialInfo
    release_name: str = field(init=False)
    above_max_size_te_found: bool | None = False
    torrent_entry: TorrentEntry | None = None
    search_id: int | None = None
    # Set when an LFM / MusicBrainz API request for this item failed at the infrastructure level (connection error,
    # unusable payload). Filters use these to attribute a data-missing skip to the failed request rather than to a
    # generic unresolved-fields / no-source-release reason.
    lfm_request_failed: bool = False
    mb_request_failed: bool = False
    # Track items only: the candidate origin releases, best-first (see `rank_origin_candidates`), and the candidate
    # whose RED release group matched.
    origin_candidates: list[OriginRelease] = field(default_factory=list)
    matched_origin: OriginRelease | None = None
    # The search trace: what each stage of the processor chain found, in order (see `plastered.models.search_trace`).
    # `persisted_trace_count` is how many leading steps `persist_search_trace` has written to the DB so far.
    trace: list[TraceStep] = field(default_factory=list)
    persisted_trace_count: int = 0
    _lfm_album_info: LFMAlbumInfo | None = None
    _mb_release: MBRelease | None = None
    _search_kwargs: OrderedDict[str, Any] = field(default_factory=OrderedDict)
    # The optional RED browse params supplied by an ad-hoc request; they win over any MB-resolved values.
    _user_search_kwargs: OrderedDict[str, Any] = field(default_factory=OrderedDict)

    def __post_init__(self):
        """
        Set the initial `release_name` value based on the instance's other attributes.
        Note: The `release_name` value may change later on for a Track rec, depending on origin-release resolution
        (see `ResolveTrackOriginModifier`, `set_origin_candidates` and `set_matched_origin`).
        For more on dataclasses and __post_init__ method, see this SO answer: https://stackoverflow.com/a/76187691
        """
        if self.initial_info.entity_type == EntityType.ALBUM.value:
            self.release_name = self.initial_info.get_human_readable_entity_str()
        else:
            self.release_name = self.origin_candidates[0].release_name if self.origin_candidates else "None"
        # Ad-hoc searches may carry user-supplied optional RED browse params; seed them up-front so they are used even
        # when no MBID resolution takes place (and so they take precedence over any MB-resolved values).
        if isinstance(self.initial_info, AdhocSearch):
            self._user_search_kwargs = self.initial_info.get_user_search_kwargs()
            self._search_kwargs = OrderedDict(self._user_search_kwargs)

    @property
    def artist_name(self) -> str:
        """Returns the human-readable artist name."""
        return self.initial_info.get_human_readable_artist_str()

    @property
    def track_name(self) -> str:
        """Returns the human-readable track name."""
        return self.initial_info.get_human_readable_track_str()

    @property
    def is_manual(self) -> bool:
        """Returns `True` if the SearchItem is an ad-hoc (non-scraper) search, otherwise `False` for an LFMRec."""
        return isinstance(self.initial_info, AdhocSearch)

    @property
    def top_origin(self) -> OriginRelease | None:
        """The best-ranked candidate origin release of a track item, or `None` (albums / unresolved tracks)."""
        return self.origin_candidates[0] if self.origin_candidates else None

    def add_trace_step(self, stage: SearchStage, outcome: SearchStepOutcome, detail: str) -> None:
        """Appends a step to the search trace."""
        self.trace.append(TraceStep(stage=stage, outcome=outcome, detail=detail))

    def get_search_kwargs(self) -> OrderedDict[str, Any]:
        return self._search_kwargs

    def get_origin_search_kwargs(self, origin: OriginRelease) -> OrderedDict[str, Any]:
        """
        The search kwargs for matching one origin candidate against RED. The MB-resolved values describe the top
        candidate, so they seed the kwargs for it only. The candidate's own release type wins over the MB release's
        (the candidate's release-group type is secondary-type aware — a soundtrack, not its "Album" primary type —
        the MB release's is not) and its own year fills a missing one. The user-supplied ad-hoc values win over
        everything, for every candidate.
        """
        kwargs: OrderedDict[str, Any] = OrderedDict(self._search_kwargs if origin == self.top_origin else {})
        if (red_release_type := origin.get_red_release_type()) is not None:
            kwargs[RED_PARAM_RELEASE_TYPE] = red_release_type.value
        if origin.release_year is not None and kwargs.get(RED_PARAM_RELEASE_YEAR) is None:
            kwargs[RED_PARAM_RELEASE_YEAR] = origin.release_year
        kwargs.update({k: v for k, v in self._user_search_kwargs.items() if v is not None})
        return kwargs

    def search_kwargs_has_all_required_fields(self, required_kwargs: set[str]) -> bool:
        """
        Return `True` if all the specified fields are set to non-empty values. Return `False` otherwise. A track item is
        judged on its top origin candidate only: the MB release lookup, which fills these fields, is made for that
        candidate, so a lower-ranked candidate carrying them cannot stand in for it.
        """
        top_origin = self.top_origin
        kwargs = self.get_origin_search_kwargs(origin=top_origin) if top_origin is not None else self._search_kwargs
        return all(kwargs.get(k) is not None for k in required_kwargs)

    def get_matched_mbid(self) -> str | None:
        """
        The MBID of the release the item resolved to. A user-supplied ad-hoc MBID wins. Otherwise the MB release
        resolved by `AttemptResolveMBReleaseModifier` is authoritative once present (it replaces a stale LFM MBID and
        canonicalizes a merged one); before that, the LFM album's / the track's top origin candidate's MBID stands
        in. A track matched via a candidate other than the top one reports that candidate's own MBID, since the MB
        release describes the top candidate only.
        """
        if isinstance(self.initial_info, AdhocSearch) and self.initial_info.mbid is not None:
            return self.initial_info.mbid
        if self.initial_info.entity_type == EntityType.ALBUM:
            if self._mb_release is not None:
                return self._mb_release.mbid
            return self._lfm_album_info.release_mbid or None if self._lfm_album_info is not None else None
        origin = self.matched_origin or self.top_origin
        if origin is not None and origin != self.top_origin:
            return origin.release_mbid or None
        if self._mb_release is not None:
            return self._mb_release.mbid
        return origin.release_mbid or None if origin is not None else None

    def found_red_match(self) -> bool:
        return self.torrent_entry is not None and not self.above_max_size_te_found

    def set_torrent_match_fields(self, torrent_match: TorrentMatch) -> None:
        self.torrent_entry = torrent_match.torrent_entry
        self.above_max_size_te_found = torrent_match.above_max_size_found

    def set_lfm_album_info(self, lfmai: LFMAlbumInfo | None) -> None:
        self._lfm_album_info = lfmai

    def set_origin_candidates(self, candidates: list[OriginRelease]) -> None:
        """Sets a track item's ranked origin candidates; the top candidate becomes the item's `release_name`."""
        self.origin_candidates = list(candidates)
        self.matched_origin = None
        if candidates:
            self.release_name = candidates[0].release_name

    def set_matched_origin(self, origin: OriginRelease) -> None:
        """Records the origin candidate whose RED release group matched; it becomes the item's `release_name`."""
        self.matched_origin = origin
        self.release_name = origin.release_name

    def set_mb_release(self, mbr: MBRelease) -> None:
        self._mb_release = mbr
        # MB-resolved params provide the baseline; any user-supplied (ad-hoc) params already on the item win on conflict.
        merged = mbr.get_release_searcher_kwargs()
        merged.update({k: v for k, v in self._search_kwargs.items() if v is not None})
        self._search_kwargs = merged
