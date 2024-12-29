from typing import Any, Dict, List, Optional
from unittest.mock import Mock

import pytest
import requests

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
)
from tests.utils_tests.conftest import api_clients_dict


@pytest.fixture(scope="session")
def red_api_client(api_clients_dict: Dict[str, requests.Session]) -> requests.Session:
    return api_clients_dict["redacted"]


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
