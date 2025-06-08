from typing import Any

import pytest

from plastered.release_search.search_helpers import SearchItem
from plastered.scraper.lfm_scraper import LFMRec
from plastered.scraper.lfm_scraper import RecContext as rc
from plastered.scraper.lfm_scraper import RecommendationType as rt
from plastered.utils.lfm_utils import LFMAlbumInfo, LFMTrackInfo


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
    "si, mb_origin_release_info_json, expected_lfmti",
    [
        pytest.param(
            SearchItem(lfm_rec=LFMRec("Artist", "Title", rt.TRACK, rc.SIMILAR_ARTIST)),
            None,
            None,
            id="Nonetype-MB-JSON",
        ),
        pytest.param(
            SearchItem(lfm_rec=LFMRec("Artist", "Title", rt.TRACK, rc.SIMILAR_ARTIST)), {}, None, id="Empty-MB-JSON"
        ),
        pytest.param(
            SearchItem(lfm_rec=LFMRec("Artist", "Title", rt.TRACK, rc.SIMILAR_ARTIST)),
            {"origin_release_mbid": "abc", "origin_release_name": "Some Album"},
            LFMTrackInfo(
                artist="Artist",
                track_name="Title",
                release_name="Some Album",
                lfm_url="https://www.last.fm/music/Artist/_/Title",
                release_mbid="abc",
            ),
            id="Full-MB-JSON",
        ),
        pytest.param(
            SearchItem(lfm_rec=LFMRec("Artist", "Title", rt.TRACK, rc.SIMILAR_ARTIST)),
            {"origin_release_mbid": "", "origin_release_name": "Some Album"},
            LFMTrackInfo(
                artist="Artist",
                track_name="Title",
                release_name="Some Album",
                lfm_url="https://www.last.fm/music/Artist/_/Title",
                release_mbid="",
            ),
            id="Empty-mbid-MB-JSON",
        ),
        pytest.param(
            SearchItem(lfm_rec=LFMRec("Artist", "Title", rt.TRACK, rc.SIMILAR_ARTIST)),
            {"origin_release_mbid": "abc", "origin_release_name": ""},
            LFMTrackInfo(
                artist="Artist",
                track_name="Title",
                release_name="",
                lfm_url="https://www.last.fm/music/Artist/_/Title",
                release_mbid="abc",
            ),
            id="Empty-release-name-MB-JSON",
        ),
    ],
)
def test_lfmti_from_mb_origin_release_info(
    si: SearchItem, mb_origin_release_info_json: dict[str, Any], expected_lfmti: LFMTrackInfo | None
) -> None:
    actual = LFMTrackInfo.from_mb_origin_release_info(si=si, mb_origin_release_info_json=mb_origin_release_info_json)
    assert actual == expected_lfmti


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


@pytest.mark.parametrize(
    "other, expected",
    [
        ("not-right-type", False),
        (
            LFMTrackInfo(
                artist="Dr. Octagon",
                track_name="Some Other Track",
                release_mbid="2271e923-291d-4dd0-96d7-3cf3f9d294ed",
                release_name="Dr. Octagonecologyst",
                lfm_url="https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst",
            ),
            False,
        ),
        (
            LFMTrackInfo(
                artist="Dr. Octagon",
                track_name="Some Track",
                release_mbid="2271e923-291d-4dd0-96d7-3cf3f9d294ed",
                release_name="Dr. Octagonecologyst",
                lfm_url="https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst",
            ),
            True,
        ),
    ],
)
def test_lfmti_eq(other: Any, expected: bool) -> None:
    test_instance = LFMTrackInfo(
        artist="Dr. Octagon",
        track_name="Some Track",
        release_mbid="2271e923-291d-4dd0-96d7-3cf3f9d294ed",
        release_name="Dr. Octagonecologyst",
        lfm_url="https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst",
    )
    actual = test_instance == other
    assert actual == expected


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


def test_lfmti_str() -> None:
    lfmti = LFMTrackInfo(
        artist="Dr. Octagon",
        track_name="Some Track",
        release_mbid="2271e923-291d-4dd0-96d7-3cf3f9d294ed",
        release_name="Some+Other+Album",
        lfm_url="https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst",
    )
    expected = "LFMTrackInfo(artist='Dr. Octagon', track_name='Some Track', release_name='Some+Other+Album', lfm_url='https://www.last.fm/music/Dr.+Octagon/Dr.+Octagonecologyst', release_mbid='2271e923-291d-4dd0-96d7-3cf3f9d294ed')"
    actual = str(lfmti)
    assert actual == expected, f"Expected str(lmfti) result to be {expected}, but got {actual}"
