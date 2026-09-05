"""
Candidate origin releases for a track search: the releases a track is known to appear on, gathered from the LFM track
info and from MusicBrainz, then ranked best-first (see `rank_origin_candidates`). A track appears on several release
groups by nature (its album, a single, later compilations, ...), so the searcher tries the candidates in rank order
against the artist's RED release groups rather than committing to a single origin release up-front — restricted to
the release types a track can originate from (`TRACK_ORIGIN_RELEASE_TYPES`): a same-titled compilation or live album
carries another version of the track at best.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from plastered.models.types import (
    RED_RELEASE_TYPE_BY_MB_SECONDARY_TYPE,
    TRACK_ORIGIN_RELEASE_TYPES,
    RedReleaseType,
    red_release_type_from_mb_types,
)
from plastered.utils.text_utils import MIN_MATCH_SCORE, normalize_title, same_name, title_match_score

_RELEASE_YEAR_PATTERN = re.compile(r"^(\d{4})")
# Ranking tiers (see `OriginRelease.rank_key`): official albums, then EPs, then singles, then soundtracks; unofficial
# releases and unknown types last.
_TIER_BY_RED_RELEASE_TYPE = {
    RedReleaseType.ALBUM: 0,
    RedReleaseType.EP: 1,
    RedReleaseType.SINGLE: 2,
    RedReleaseType.SOUNDTRACK: 3,
}
_TIER_UNKNOWN = 4


class OriginSource(StrEnum):
    """Where a track's candidate origin release came from."""

    LFM = "lfm_track_info"
    MB_RECORDING_LOOKUP = "mb_recording_lookup"
    MB_RECORDING_SEARCH = "mb_recording_search"


@dataclass(frozen=True)
class OriginRelease:
    """One release a track is known to appear on. MB-sourced candidates carry the release-group type / date data."""

    release_name: str
    source: OriginSource
    release_mbid: str | None = None
    release_group_mbid: str | None = None
    primary_type: str | None = None
    secondary_types: tuple[str, ...] = ()
    status: str | None = None
    # The release's own date and its release group's first release date ("YYYY[-MM[-DD]]"), when known.
    release_date: str | None = None
    first_release_date: str | None = None

    @classmethod
    def from_lfm_track_info(cls, json_blob: dict[str, Any]) -> OriginRelease | None:
        """The release LFM associates with the track (the `track.getinfo` `album`), or `None` when LFM has none."""
        album_json = json_blob.get("album")
        if not isinstance(album_json, dict) or not album_json.get("title"):
            return None
        return cls(
            release_name=album_json["title"], source=OriginSource.LFM, release_mbid=album_json.get("mbid") or None
        )

    @classmethod
    def from_mb_release_json(cls, release_json: dict[str, Any], source: OriginSource) -> OriginRelease | None:
        """A release object of an MB recording lookup / search response, or `None` when it carries no title."""
        title = release_json.get("title")
        if not title:
            return None
        release_group_json = release_json.get("release-group") or {}
        return cls(
            release_name=title,
            source=source,
            release_mbid=release_json.get("id") or None,
            release_group_mbid=release_group_json.get("id") or None,
            primary_type=release_group_json.get("primary-type") or None,
            secondary_types=tuple(release_group_json.get("secondary-types") or ()),
            status=release_json.get("status") or None,
            release_date=release_json.get("date") or None,
            first_release_date=release_group_json.get("first-release-date") or None,
        )

    @property
    def origin_date(self) -> str | None:
        """The date the release group was first released, falling back to the release's own date."""
        return self.first_release_date or self.release_date

    @property
    def release_year(self) -> int | None:
        year_match = _RELEASE_YEAR_PATTERN.match(self.origin_date or "")
        return int(year_match.group(1)) if year_match else None

    def get_red_release_type(self) -> RedReleaseType | None:
        """The RED release type of the release group (see `red_release_type_from_mb_types`); `None` when unknown."""
        return red_release_type_from_mb_types(primary_type=self.primary_type, secondary_types=self.secondary_types)

    @property
    def is_track_origin_type(self) -> bool:
        """
        Whether the release group is of a type a track can originate from (`TRACK_ORIGIN_RELEASE_TYPES`). Any RED-mapped
        secondary type outside that set (compilation, live, remix, ...) rules the group out; MB primary types map to
        allowed RED types or none. An unknown type passes: the RED-side type restriction of
        `SearchState.get_candidate_release_groups` still applies to its matches.
        """
        secondary_red_release_types = {
            red_release_type
            for secondary_type in self.secondary_types
            if (red_release_type := RED_RELEASE_TYPE_BY_MB_SECONDARY_TYPE.get(secondary_type.casefold())) is not None
        }
        return secondary_red_release_types <= TRACK_ORIGIN_RELEASE_TYPES

    @property
    def dedupe_key(self) -> str:
        """Identity for deduping candidates: the release group, falling back to the normalized title."""
        return self.release_group_mbid or f"title:{normalize_title(self.release_name)}"

    def rank_key(self) -> tuple[int, bool, str, bool, str]:
        """
        Sort key ordering candidates best-first: tier, then the earliest origin date, then the earliest release date
        (so the original release of a group beats its reissues); undated entries sort last within a tier.
        """
        # An unknown status is not evidence of an unofficial release, so only an explicit non-official status demotes.
        is_official = self.status is None or self.status.casefold() == "official"
        tier = _TIER_UNKNOWN
        if is_official and (red_release_type := self.get_red_release_type()) is not None:
            tier = _TIER_BY_RED_RELEASE_TYPE.get(red_release_type, _TIER_UNKNOWN)
        origin_date, release_date = self.origin_date, self.release_date
        return (tier, origin_date is None, origin_date or "", release_date is None, release_date or "")


def artist_credit_matches(
    artist_credit_json: list[dict[str, Any]] | None, artist_name: str, artist_mbid: str | None = None
) -> bool:
    """
    Whether an MB artist credit names the wanted artist: by artist MBID when one is known, else by normalized name —
    either one credited artist or the credit as a whole (e.g. "A & B").
    """
    credits = artist_credit_json or []
    for credit_json in credits:
        artist_json = credit_json.get("artist") or {}
        if artist_mbid and artist_json.get("id") == artist_mbid:
            return True
        credited_names = (credit_json.get("name"), artist_json.get("name"), artist_json.get("sort-name"))
        if any(name and same_name(name, artist_name) for name in credited_names):
            return True
    joined_credit = "".join(f"{c.get('name') or ''}{c.get('joinphrase') or ''}" for c in credits)
    return bool(joined_credit) and same_name(joined_credit, artist_name)


def _recording_title_matches(recording_title: str | None, track_name: str) -> bool:
    if not recording_title:
        return False
    return (
        title_match_score(wanted_title=track_name, candidate_title=recording_title, fuzzy_enabled=True)
        >= MIN_MATCH_SCORE
    )


def origin_releases_from_recording(
    recording_json: dict[str, Any],
    source: OriginSource,
    artist_name: str,
    artist_mbid: str | None = None,
    track_name: str | None = None,
) -> list[OriginRelease]:
    """
    The candidate origin releases of one MB recording object (from a recording lookup or search response). Empty
    unless the recording is credited to the wanted artist and, when `track_name` is given, titled like the track.
    The title check is lenient (`title_match_score` with the fuzzy tiers): LFM track names often carry featured-artist
    / remaster / version suffixes that MB recording titles omit, and vice versa.
    """
    if track_name is not None and not _recording_title_matches(recording_json.get("title"), track_name=track_name):
        return []
    if not artist_credit_matches(recording_json.get("artist-credit"), artist_name=artist_name, artist_mbid=artist_mbid):
        return []
    candidates: list[OriginRelease] = []
    for release_json in recording_json.get("releases") or []:
        if (candidate := OriginRelease.from_mb_release_json(release_json=release_json, source=source)) is not None:
            candidates.append(candidate)
    return candidates


def rank_origin_candidates(
    mb_candidates: list[OriginRelease], lfm_candidate: OriginRelease | None = None
) -> list[OriginRelease]:
    """
    Dedupes the candidates by release group (keeping each group's best-ranked release), drops those of a type a track
    cannot originate from (`OriginRelease.is_track_origin_type`) and orders the rest best-first per
    `OriginRelease.rank_key`. The LFM candidate is folded into an MB candidate sharing its release MBID or normalized
    title — so an LFM album MB knows as e.g. a compilation is dropped along with it; otherwise it is kept as its own
    (type-less, hence last-tier) candidate.
    """
    best_by_key: dict[str, OriginRelease] = {}
    for candidate in mb_candidates:
        current = best_by_key.get(candidate.dedupe_key)
        if current is None or candidate.rank_key() < current.rank_key():
            best_by_key[candidate.dedupe_key] = candidate
    if lfm_candidate is not None:
        known_mbids = {c.release_mbid for c in mb_candidates if c.release_mbid}
        known_titles = {normalize_title(c.release_name) for c in best_by_key.values()}
        if (
            lfm_candidate.release_mbid not in known_mbids
            and normalize_title(lfm_candidate.release_name) not in known_titles
        ):
            best_by_key[lfm_candidate.dedupe_key] = lfm_candidate
    # `sorted` is stable, so equally-ranked candidates keep their source order (lookup / search results, then LFM).
    return sorted((c for c in best_by_key.values() if c.is_track_origin_type), key=OriginRelease.rank_key)
