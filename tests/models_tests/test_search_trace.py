import pytest

from plastered.models import OriginRelease, OriginSource, RedReleaseType, ReleaseEntry, SearchStage, TorrentEntry
from plastered.models.search_trace import (
    counted,
    origin_label,
    quoted,
    release_group_label,
    release_type_name,
    torrent_label,
)
from plastered.utils.constants import BYTES_IN_GB


@pytest.mark.parametrize("stage", list(SearchStage))
def test_every_stage_has_a_display_name(stage: SearchStage) -> None:
    assert stage.display_name and stage.display_name != stage.value


def test_quoted_and_counted() -> None:
    assert quoted("Some Album") == '"Some Album"'
    assert counted(1, "release group") == "1 release group"
    assert counted(0, "candidate") == "0 candidates"
    assert counted(3, "candidate") == "3 candidates"
    assert counted(1, "title match") == "1 title match"
    assert counted(2, "title match") == "2 title matches"


@pytest.mark.parametrize(
    "release_type, expected",
    [
        (None, "unknown type"),
        (RedReleaseType.ALBUM, "album"),
        (RedReleaseType.EP, "EP"),
        (RedReleaseType.LIVE_ALBUM, "live album"),
        (RedReleaseType.DJ_MIX, "DJ mix"),
    ],
)
def test_release_type_name(release_type: RedReleaseType | None, expected: str) -> None:
    assert release_type_name(release_type) == expected


def test_origin_label_includes_the_known_qualifiers() -> None:
    typed_and_dated = OriginRelease(
        release_name="Album", source=OriginSource.MB_RECORDING_LOOKUP, primary_type="Album", release_date="1996-05-07"
    )
    assert origin_label(typed_and_dated) == '"Album" (album, 1996)'
    typed_only = OriginRelease(release_name="Single", source=OriginSource.MB_RECORDING_SEARCH, primary_type="Single")
    assert origin_label(typed_only) == '"Single" (single)'
    dated_only = OriginRelease(release_name="Album", source=OriginSource.MB_RECORDING_SEARCH, release_date="2001")
    assert origin_label(dated_only) == '"Album" (2001)'
    assert origin_label(OriginRelease(release_name="LFM Album", source=OriginSource.LFM)) == '"LFM Album"'


def test_release_group_label() -> None:
    dated = ReleaseEntry(group_id=1, group_name="Album", release_type=RedReleaseType.EP, group_year=2001)
    assert release_group_label(dated) == '"Album" (EP, 2001)'
    undated = ReleaseEntry(group_id=2, group_name="Album", release_type=RedReleaseType.SOUNDTRACK)
    assert release_group_label(undated) == '"Album" (soundtrack)'


def test_torrent_label() -> None:
    te = TorrentEntry(
        torrent_id=123,
        media="WEB",
        format="FLAC",
        encoding="Lossless",
        size=0,
        scene=False,
        trumpable=False,
        has_snatched=False,
        has_log=False,
        log_score=0,
        has_cue=False,
        can_use_token=False,
    )
    te.size = 0.42 * BYTES_IN_GB
    assert torrent_label(te) == "torrent 123 (WEB / FLAC / Lossless, 0.42 GB)"
