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
    RedFormatPreferences,
    RedReleaseType,
    ReleaseEntry,
    TorrentEntry,
    create_browse_params,
)
from tests.conftest import (
    expected_red_format_list,
    mock_red_browse_empty_response,
    mock_red_browse_non_empty_response,
    mock_red_group_response,
)
from tests.utils_tests.conftest import api_clients_dict


@pytest.fixture(scope="session")
def red_api_client(api_clients_dict: Dict[str, requests.Session]) -> requests.Session:
    return api_clients_dict["redacted"]


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


def test_from_torrent_group_json_blob_invalid_edition(mock_red_group_response: Dict[str, Any]) -> None:
    invalid_edition_id = 69420
    with pytest.raises(ValueError, match="Invalid edition ID provided for torrent group ID"):
        ReleaseEntry.from_torrent_group_json_blob(json_blob=mock_red_group_response, edition_id=invalid_edition_id)


@pytest.mark.parametrize(
    "mock_torrent_entries, expected",
    [
        (
            [
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
                ),
                TorrentEntry(
                    torrent_id=949473,
                    media=MediaEnum.CD.value,
                    format=FormatEnum.MP3.value,
                    encoding=EncodingEnum.MP3_320.value,
                    size=1109018,
                    scene=False,
                    trumpable=False,
                    has_snatched=False,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    reported=False,
                    lossy_web=False,
                    lossy_master=False,
                ),
            ],
            False,
        ),
        (
            [
                TorrentEntry(
                    torrent_id=949473,
                    media=MediaEnum.CD.value,
                    format=FormatEnum.FLAC.value,
                    encoding=EncodingEnum.LOSSLESS.value,
                    size=110902818,
                    scene=False,
                    trumpable=False,
                    has_snatched=True,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    reported=False,
                    lossy_web=False,
                    lossy_master=False,
                ),
            ],
            True,
        ),
        (
            [
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
                ),
                TorrentEntry(
                    torrent_id=949473,
                    media=MediaEnum.CD.value,
                    format=FormatEnum.MP3.value,
                    encoding=EncodingEnum.MP3_320.value,
                    size=1109018,
                    scene=False,
                    trumpable=False,
                    has_snatched=True,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    reported=False,
                    lossy_web=False,
                    lossy_master=False,
                ),
            ],
            True,
        ),
    ],
)
def test_release_entry_has_snatched_any(
    mock_torrent_entries: List[TorrentEntry],
    expected: bool,
) -> None:
    test_release_entry = ReleaseEntry(
        group_id=463161,
        media=MediaEnum.CD.value,
        remastered=True,
        remaster_year=2000,
        remaster_title="Promo",
        remaster_catalogue_number="CSK 48775",
        release_type=RedReleaseType.SINGLE,
        remaster_record_label="Track Masters &lrm;/ Columbia",
        torrent_entries=mock_torrent_entries,
    )
    actual = test_release_entry.has_snatched_any()
    assert (
        actual == expected
    ), f"Expected tetest_release_entry.has_snatched_any() to return {expected}, but got {actual}"


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


@pytest.mark.parametrize(
    "mock_response_fixture_names, mock_preference_ordering, expected_torrent_entry",
    [
        (  # Test case 1: empty browse results for first/only preference
            ["mock_red_browse_empty_response"],
            [RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.SACD)],
            None,
        ),
        (  # Test case 2: non-empty browse results for first preference
            ["mock_red_browse_non_empty_response"],
            [RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB)],
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
        ),
        (  # Test case 3: empty browse results for first pref, and non-empty browse results for 2nd preference
            ["mock_red_browse_empty_response", "mock_red_browse_non_empty_response"],
            [
                RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.SACD),
                RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
            ],
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
        ),
    ],
)  # TODO: Add test case for size over max_size filtering
def test_search_release_by_preferences(
    request: pytest.FixtureRequest,
    red_api_client: requests.Session,
    mock_response_fixture_names: List[str],
    mock_preference_ordering: List[RedFormat],
    expected_torrent_entry: Optional[TorrentEntry],
) -> None:
    red_api_client.get = Mock(
        name="get", side_effect=[request.getfixturevalue(fixture_name) for fixture_name in mock_response_fixture_names]
    )
    rfp = RedFormatPreferences(preference_ordering=mock_preference_ordering)
    actual_torrent_entry = rfp.search_release_by_preferences(
        red_client=red_api_client,
        artist_name="Fake+Artist",
        album_name="Fake+Release",
        release_type=RedReleaseType.ALBUM,
        first_release_year=1899,
    )
    assert actual_torrent_entry == expected_torrent_entry


@pytest.mark.parametrize(
    "red_format, release_type, first_release_year, record_label, catalog_number, expected_browse_params",
    [
        (
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
            None,
            None,
            None,
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc",
        ),
        (
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.LOSSLESS, media=MediaEnum.WEB),
            None,
            None,
            None,
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc",
        ),
        (
            RedFormat(format=FormatEnum.MP3, encoding=EncodingEnum.MP3_V0, media=MediaEnum.WEB),
            None,
            None,
            None,
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=MP3&encoding=V0+(VBR)&media=WEB&group_results=1&order_by=seeders&order_way=desc",
        ),
        (
            RedFormat(format=FormatEnum.MP3, encoding=EncodingEnum.MP3_V0, media=MediaEnum.CD),
            None,
            None,
            None,
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=MP3&encoding=V0+(VBR)&media=CD&group_results=1&order_by=seeders&order_way=desc",
        ),
        (
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
            RedReleaseType.ALBUM,
            None,
            None,
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc&releasetype=1",
        ),
        (
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
            None,
            1969,
            None,
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc&year=1969",
        ),
        (
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
            None,
            None,
            "Fake Label",
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc&recordlabel=Fake+Label",
        ),
        (
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
            None,
            None,
            None,
            "FL 69420",
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc&cataloguenumber=FL+69420",
        ),
    ],
)
def test_create_browse_params(
    red_format: RedFormat,
    release_type: Optional[RedReleaseType],
    first_release_year: Optional[int],
    record_label: Optional[str],
    catalog_number: Optional[str],
    expected_browse_params: str,
) -> None:
    fake_artist_name = "Some+Artist"
    fake_album_name = "Some+Bad+Album"
    actual_browse_params = create_browse_params(
        red_format=red_format,
        artist_name=fake_artist_name,
        album_name=fake_album_name,
        release_type=release_type,
        first_release_year=first_release_year,
        record_label=record_label,
        catalog_number=catalog_number,
    )
    assert (
        actual_browse_params == expected_browse_params
    ), f"Expected browse params to be '{expected_browse_params}', but got '{actual_browse_params}' instead."
