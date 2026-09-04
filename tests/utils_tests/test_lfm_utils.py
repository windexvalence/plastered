from typing import Any

import pytest

from plastered.models.lfm_models import LFMAlbumInfo


def test_construct_from_api_response(mock_lfm_album_info_json: dict[str, Any]) -> None:
    expected_lfmai = LFMAlbumInfo(
        artist="Dr. Octagon",
        release_mbid="2271e923-291d-4dd0-96d7-3cf3f9d294ed",
        album_name="Dr. Octagonecologyst",
        lfm_url="https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst",
    )
    actual_lfmai = LFMAlbumInfo.construct_from_api_response(json_blob=mock_lfm_album_info_json["album"])
    assert actual_lfmai == expected_lfmai, (
        f"Expected LFMAlbumInfo to be '{str(expected_lfmai)}', but got '{str(actual_lfmai)}'"
    )


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
def test_lfmai_eq(other: Any, expected: bool) -> None:
    test_instance = LFMAlbumInfo(
        artist="Dr. Octagon",
        release_mbid="2271e923-291d-4dd0-96d7-3cf3f9d294ed",
        album_name="Dr. Octagonecologyst",
        lfm_url="https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst",
    )
    actual = test_instance == other
    assert actual == expected, f"Expected {test_instance}.__eq__(other={other}) to be {expected}, but got {actual}"


def test_lfmai_str() -> None:
    lfmai = LFMAlbumInfo(
        artist="Dr. Octagon",
        release_mbid="2271e923-291d-4dd0-96d7-3cf3f9d294ed",
        album_name="Some+Other+Album",
        lfm_url="https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst",
    )
    # expected = "{'artist': 'Dr. Octagon', 'album_name': 'Some+Other+Album', 'lfm_url': 'https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst', 'release_mbid': '2271e923-291d-4dd0-96d7-3cf3f9d294ed'}"
    expected = "LFMAlbumInfo(artist='Dr. Octagon', album_name='Some+Other+Album', lfm_url='https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst', release_mbid='2271e923-291d-4dd0-96d7-3cf3f9d294ed')"
    actual = str(lfmai)
    assert actual == expected, f"Expected str(lmfti) result to be {expected}, but got {actual}"
