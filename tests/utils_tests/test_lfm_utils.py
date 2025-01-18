from typing import Any, Dict

import pytest

from plastered.utils.lfm_utils import LFMAlbumInfo
from tests.conftest import mock_lfm_album_info_json


def test_construct_from_api_response(mock_lfm_album_info_json: Dict[str, Any]) -> None:
    expected_lfmai = LFMAlbumInfo(
        artist="Dr. Octagon",
        release_mbid="2271e923-291d-4dd0-96d7-3cf3f9d294ed",
        album_name="Dr. Octagonecologyst",
        lfm_url="https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst",
    )
    actual_lfmai = LFMAlbumInfo.construct_from_api_response(json_blob=mock_lfm_album_info_json["album"])
    assert (
        actual_lfmai == expected_lfmai
    ), f"Expected LFMAlbumInfo to be '{str(expected_lfmai)}', but got '{str(actual_lfmai)}'"


@pytest.mark.parametrize(
    "other, expected",
    [
        ("not-right-type", False),
        (
            LFMAlbumInfo(
                artist="Dr. Octagon",
                release_mbid="2271e923-291d-4dd0-96d7-3cf3f9d294ed",
                album_name="Some+Other+Album",
                lfm_url="https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst",
            ),
            False,
        ),
        (
            LFMAlbumInfo(
                artist="Dr. Octagon",
                release_mbid="2271e923-291d-4dd0-96d7-3cf3f9d294ed",
                album_name="Dr. Octagonecologyst",
                lfm_url="https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst",
            ),
            True,
        ),
    ],
)
def test_eq(other: Any, expected: bool) -> None:
    test_instance = LFMAlbumInfo(
        artist="Dr. Octagon",
        release_mbid="2271e923-291d-4dd0-96d7-3cf3f9d294ed",
        album_name="Dr. Octagonecologyst",
        lfm_url="https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst",
    )
    actual = test_instance.__eq__(other)
    assert actual == expected, f"Expected {test_instance}.__eq__(other={other}) to be {expected}, but got {actual}"


def test_str() -> None:
    lfmai = LFMAlbumInfo(
        artist="Dr. Octagon",
        release_mbid="2271e923-291d-4dd0-96d7-3cf3f9d294ed",
        album_name="Some+Other+Album",
        lfm_url="https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst",
    )
    expected = "{'_artist': 'Dr. Octagon', '_album_name': 'Some+Other+Album', '_lfm_url': 'https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst', '_release_mbid': '2271e923-291d-4dd0-96d7-3cf3f9d294ed'}"
    actual = lfmai.__str__()
    assert actual == expected, f"Expected __str__() method result to be {expected}, but got {actual}"
