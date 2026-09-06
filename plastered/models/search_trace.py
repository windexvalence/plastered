"""
The trace of a release search: one `TraceStep` per stage of the processor chain, recorded on the `SearchItem` as the
chain runs and persisted as `SearchStep` rows (see `plastered.db.db_utils.persist_search_trace`). The ad-hoc search
page renders it, so a search that finds no release shows what each stage found and where it stopped.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from plastered.models.types import RedReleaseType

if TYPE_CHECKING:
    from plastered.models.origin_release import OriginRelease
    from plastered.models.red_models import ReleaseEntry, TorrentEntry


class SearchStage(StrEnum):
    """
    The stages of a release search, in the order the processor chain runs them (album and track chains differ).
    `SearchStep` rows store members by name, so a member MUST be retained (never renamed) for historical rows to
    still deserialize.
    """

    LFM_TRACK_INFO = "lfm_track_info"
    MB_RECORDING = "mb_recording"
    TRACK_ORIGIN = "track_origin"
    PRIOR_SNATCH = "prior_snatch"
    LFM_ALBUM_INFO = "lfm_album_info"
    MB_RELEASE = "mb_release"
    REQUIRED_FIELDS = "required_fields"
    RED_ARTIST = "red_artist"
    RED_MATCH = "red_match"

    @property
    def display_name(self) -> str:
        return _STAGE_DISPLAY_NAMES[self]


_STAGE_DISPLAY_NAMES: Final[dict[SearchStage, str]] = {
    SearchStage.LFM_TRACK_INFO: "Last.fm track lookup",
    SearchStage.MB_RECORDING: "MusicBrainz recording lookup",
    SearchStage.TRACK_ORIGIN: "Track origin resolution",
    SearchStage.PRIOR_SNATCH: "Prior-snatch check",
    SearchStage.LFM_ALBUM_INFO: "Last.fm album lookup",
    SearchStage.MB_RELEASE: "MusicBrainz release lookup",
    SearchStage.REQUIRED_FIELDS: "Required search fields",
    SearchStage.RED_ARTIST: "RED artist lookup",
    SearchStage.RED_MATCH: "RED release matching",
}


class SearchStepOutcome(StrEnum):
    """
    How a stage went: as intended, degraded but the search went on (`WARNING`), or the search ended there. Stored by
    name like `SearchStage`, so members MUST be retained.
    """

    OK = "ok"
    WARNING = "warning"
    STOPPED = "stopped"


@dataclass(frozen=True)
class TraceStep:
    stage: SearchStage
    outcome: SearchStepOutcome
    detail: str


def quoted(text: str) -> str:
    return f'"{text}"'


def counted(count: int, noun: str) -> str:
    """`1 release group` / `3 release groups` / `2 title matches`."""
    if count == 1:
        return f"1 {noun}"
    suffix = "es" if noun.endswith(("ch", "sh", "s", "x")) else "s"
    return f"{count} {noun}{suffix}"


_CASED_RELEASE_TYPE_NAMES: Final[dict[RedReleaseType, str]] = {RedReleaseType.EP: "EP", RedReleaseType.DJ_MIX: "DJ mix"}


def release_type_name(release_type: RedReleaseType | None) -> str:
    """`album`, `EP`, `live album`, ...; `unknown type` for `None`."""
    if release_type is None:
        return "unknown type"
    return _CASED_RELEASE_TYPE_NAMES.get(release_type, release_type.name.replace("_", " ").lower())


def _release_label(title: str, release_type: RedReleaseType | None, year: int | None) -> str:
    qualifiers = [release_type_name(release_type)] if release_type is not None else []
    if year is not None:
        qualifiers.append(str(year))
    return f"{quoted(title)} ({', '.join(qualifiers)})" if qualifiers else quoted(title)


def origin_label(origin: OriginRelease) -> str:
    """`"Album" (album, 1996)`, with whichever of the release type and year are known."""
    return _release_label(
        title=origin.release_name, release_type=origin.get_red_release_type(), year=origin.release_year
    )


def release_group_label(entry: ReleaseEntry) -> str:
    """`"Album" (album, 1996)` for a RED release group."""
    return _release_label(title=entry.group_name, release_type=entry.release_type, year=entry.group_year)


def torrent_label(torrent_entry: TorrentEntry) -> str:
    """`torrent 123 (WEB / FLAC / Lossless, 0.42 GB)`."""
    return (
        f"torrent {torrent_entry.torrent_id} ({torrent_entry.media} / {torrent_entry.format} / "
        f"{torrent_entry.encoding}, {torrent_entry.get_size(unit='GB'):.2f} GB)"
    )
