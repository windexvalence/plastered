from typing import Any, Dict

import pytest

from lastfm_recs_scraper.utils.lastfm_utils import LastFMAlbumInfo
from tests.conftest import mock_last_fm_album_info_json


def test_construct_from_api_response(mock_last_fm_album_info_json: Dict[str, Any]) -> None:
    expected_lfmai = LastFMAlbumInfo(
        artist="Dr. Octagon",
        release_mbid="2271e923-291d-4dd0-96d7-3cf3f9d294ed",
        album_name="Dr. Octagonecologyst",
        lastfm_url="https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst",
    )
    actual_lfmai = LastFMAlbumInfo.construct_from_api_response(json_blob=mock_last_fm_album_info_json["album"])
    assert (
        actual_lfmai == expected_lfmai
    ), f"Expected LastFMAlbumInfo to be '{str(expected_lfmai)}', but got '{str(actual_lfmai)}'"


@pytest.mark.parametrize(
    "other, expected",
    [
        ("not-right-type", False),
        (
            LastFMAlbumInfo(
                artist="Dr. Octagon",
                release_mbid="2271e923-291d-4dd0-96d7-3cf3f9d294ed",
                album_name="Some+Other+Album",
                lastfm_url="https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst",
            ),
            False,
        ),
        (
            LastFMAlbumInfo(
                artist="Dr. Octagon",
                release_mbid="2271e923-291d-4dd0-96d7-3cf3f9d294ed",
                album_name="Dr. Octagonecologyst",
                lastfm_url="https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst",
            ),
            True,
        ),
    ],
)
def test_eq(other: Any, expected: bool) -> None:
    test_instance = LastFMAlbumInfo(
        artist="Dr. Octagon",
        release_mbid="2271e923-291d-4dd0-96d7-3cf3f9d294ed",
        album_name="Dr. Octagonecologyst",
        lastfm_url="https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst",
    )
    actual = test_instance.__eq__(other)
    assert actual == expected, f"Expected {test_instance}.__eq__(other={other}) to be {expected}, but got {actual}"


def test_str() -> None:
    lfmai = LastFMAlbumInfo(
        artist="Dr. Octagon",
        release_mbid="2271e923-291d-4dd0-96d7-3cf3f9d294ed",
        album_name="Some+Other+Album",
        lastfm_url="https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst",
    )
    expected = "{'_artist': 'Dr. Octagon', '_release_mbid': '2271e923-291d-4dd0-96d7-3cf3f9d294ed', '_album_name': 'Some+Other+Album', '_lastfm_url': 'https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst'}"
    actual = lfmai.__str__()
    assert actual == expected, f"Expected __str__() method result to be {expected}, but got {actual}"
