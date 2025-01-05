from typing import Any, Dict, List, Optional
from unittest.mock import Mock, patch

import pytest
import requests

from lastfm_recs_scraper.utils.constants import STORAGE_UNIT_IDENTIFIERS
from lastfm_recs_scraper.utils.red_utils import (
    EncodingEnum,
    FormatEnum,
    MediaEnum,
    RedFormat,
    RedReleaseType,
    ReleaseEntry,
    TorrentEntry,
)
from tests.conftest import (
    expected_red_format_list,
    mock_red_browse_empty_response,
    mock_red_browse_non_empty_response,
    mock_red_group_response,
)


@pytest.mark.parametrize(
    "other, expected",
    [
        ("not-right-type", False),
        (RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB), False),
        (RedFormat(format=FormatEnum.MP3, encoding=EncodingEnum.MP3_V0, media=MediaEnum.WEB), True),
    ],
)
def test_red_format_eq(other: Any, expected: bool) -> None:
    test_instance = RedFormat(format=FormatEnum.MP3, encoding=EncodingEnum.MP3_V0, media=MediaEnum.WEB)
    actual = test_instance.__eq__(other)
    assert actual == expected, f"Expected {test_instance}.__eq__(other={other}) to be {expected}, but got {actual}"


@pytest.mark.parametrize(
    "te, expected_cd_only_extras",
    [
        (
            TorrentEntry(
                torrent_id=69420,
                media="WEB",
                format="FLAC",
                encoding="24bit Lossless",
                size=69420,
                scene=False,
                trumpable=False,
                has_snatched=False,
                has_log=False,
                log_score=0,
                has_cue=False,
                reported=None,
                lossy_web=None,
                lossy_master=None,
            ),
            "",
        ),
        (
            TorrentEntry(
                torrent_id=69420,
                media="CD",
                format="FLAC",
                encoding="Lossless",
                size=69420,
                scene=False,
                trumpable=False,
                has_snatched=False,
                has_log=True,
                log_score=100,
                has_cue=True,
                reported=None,
                lossy_web=None,
                lossy_master=None,
            ),
            "haslog=100&hascue=1",
        ),
    ],
)
def test_torrent_entry_cd_only_extras_constructor(te: TorrentEntry, expected_cd_only_extras: str) -> None:
    actual_cd_only_extras = te.red_format._cd_only_extras
    assert (
        actual_cd_only_extras == expected_cd_only_extras
    ), f"Expected cd_only_extras to be '{expected_cd_only_extras}', but got '{actual_cd_only_extras}'"


@pytest.mark.parametrize(
    "other, expected",
    [
        ("not-right-type", False),
        (
            TorrentEntry(
                torrent_id=69420,
                media="WEB",
                format="FLAC",
                encoding="Lossless",
                size=69420,
                scene=False,
                trumpable=False,
                has_snatched=False,
                has_log=True,
                log_score=100,
                has_cue=True,
                reported=None,
                lossy_web=None,
                lossy_master=None,
            ),
            False,
        ),
        (
            TorrentEntry(
                torrent_id=69420,
                media="CD",
                format="FLAC",
                encoding="Lossless",
                size=69420,
                scene=False,
                trumpable=False,
                has_snatched=False,
                has_log=True,
                log_score=100,
                has_cue=True,
                reported=None,
                lossy_web=None,
                lossy_master=None,
            ),
            True,
        ),
    ],
)
def test_eq(other: Any, expected: bool) -> None:
    test_instance = TorrentEntry(
        torrent_id=69420,
        media="CD",
        format="FLAC",
        encoding="Lossless",
        size=69420,
        scene=False,
        trumpable=False,
        has_snatched=False,
        has_log=True,
        log_score=100,
        has_cue=True,
        reported=None,
        lossy_web=None,
        lossy_master=None,
    )
    actual = test_instance.__eq__(other)
    assert actual == expected, f"Expected {test_instance}.__eq__(other={other}) to be {expected}, but got {actual}"


@pytest.mark.parametrize(
    "unit, expected, should_fail, exception, exception_msg",
    [
        ("B", 3000000.0, False, None, None),
        ("MB", 3.0, False, None, None),
        ("GB", 0.003, False, None, None),
        ("TB", None, True, ValueError, "Unexpected unit_identifier provided"),
    ],
)
def test_torrent_entry_get_size(
    unit: str,
    expected: Optional[float],
    should_fail: bool,
    exception: Optional[Exception],
    exception_msg: Optional[str],
) -> None:
    mock_size_bytes = 3000000.0
    test_instance = TorrentEntry(
        torrent_id=69420,
        media="CD",
        format="FLAC",
        encoding="Lossless",
        size=mock_size_bytes,
        scene=False,
        trumpable=False,
        has_snatched=False,
        has_log=True,
        log_score=100,
        has_cue=True,
        reported=None,
        lossy_web=None,
        lossy_master=None,
    )
    if should_fail:
        with pytest.raises(exception, match=exception_msg):
            test_instance.get_size(unit=unit)
    else:
        actual = test_instance.get_size(unit=unit)
        assert actual == expected, f"Expected get_size(unit='{unit}') to return {expected}, but got {actual}"


def test_torrent_entry_get_red_format() -> None:
    test_instance = TorrentEntry(
        torrent_id=69420,
        media="CD",
        format="FLAC",
        encoding="Lossless",
        size=666000,
        scene=False,
        trumpable=False,
        has_snatched=False,
        has_log=True,
        log_score=100,
        has_cue=True,
        reported=None,
        lossy_web=None,
        lossy_master=None,
    )
    expected_red_format = RedFormat(
        format=FormatEnum.FLAC,
        encoding=EncodingEnum.LOSSLESS,
        media=MediaEnum.CD,
        cd_only_extras="haslog=100&hascue=1",
    )
    actual_red_format = test_instance.get_red_format()
    assert (
        actual_red_format == expected_red_format
    ), f"Expected test_instance.get_red_format() to be '{str(expected_red_format)}', but got '{str(actual_red_format)}'"


def test_release_entry_get_red_formats(mock_red_group_response: Dict[str, Any]) -> None:
    test_release_entry = ReleaseEntry(
        group_id=463161,
        media=MediaEnum.CD.value,
        remastered=True,
        remaster_year=2000,
        remaster_title="Promo",
        remaster_catalogue_number="CSK 48775",
        release_type=RedReleaseType.SINGLE,
        remaster_record_label="Track Masters &lrm;/ Columbia",
        torrent_entries=[
            TorrentEntry(
                torrent_id=949473,
                media=MediaEnum.CD.value,
                format=FormatEnum.FLAC.value,
                encoding=EncodingEnum.LOSSLESS.value,
                size=110902818,
                scene=False,
                trumpable=False,
                has_snatched=False,
                has_log=True,
                log_score=100,
                has_cue=True,
                reported=False,
                lossy_web=False,
                lossy_master=False,
            )
        ],
    )
    expected_red_format_list = [
        RedFormat(
            format=FormatEnum.FLAC,
            encoding=EncodingEnum.LOSSLESS,
            media=MediaEnum.CD,
            cd_only_extras="haslog=100&hascue=1",
        )
    ]
    actual_red_format_list = test_release_entry.get_red_formats()
    assert (
        actual_red_format_list == expected_red_format_list
    ), f"Expected test_release_entry.get_red_formats() to return {expected_red_format_list}, but got {actual_red_format_list}"
