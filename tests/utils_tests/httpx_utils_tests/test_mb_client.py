import re
from typing import Any
from unittest.mock import Mock

import pytest
from pytest_httpx import HTTPXMock

from plastered.config.app_settings import AppSettings
from plastered.utils.exceptions import MusicBrainzClientException
from plastered.utils.httpx_utils.musicbrainz_client import MusicBrainzAPIClient


@pytest.fixture(scope="session")
def mb_track_response_raise_index_error() -> dict[str, Any]:
    return {"recordings": []}


@pytest.fixture(scope="session")
def mb_track_response_raise_key_error() -> dict[str, Any]:
    return {"recordings": [{"missing_releases_key": True}]}


@pytest.mark.parametrize("expected_mbid", ["d211379d-3203-47ed-a0c5-e564815bb45a"])
def test_request_musicbrainz_api(valid_app_settings: AppSettings, expected_mbid: str) -> None:
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle")
    mb_client._throttle.return_value = None
    result = mb_client.request_release_details(mbid=expected_mbid)
    mb_client._throttle.assert_called_once()
    assert isinstance(result, dict), f"Expected result from request_api to be a dict, but was: {type(result)}"
    assert "id" in result.keys(), "Missing expected top-level key in musicbrainz response: 'id'"
    response_mbid = result["id"]
    assert response_mbid == expected_mbid, (
        f"Mismatch between actual response mbid ('{response_mbid}') and expected mbid ('{expected_mbid}')"
    )


@pytest.mark.parametrize(
    "track_name, artist_mbid, artist_name, expected",
    [
        ("Some Track", "69-420abc", "Some Artist", "recording:Some%20Track%20AND%20arid:69-420abc"),
        ("Some Track", None, "Some Artist", "recording:Some%20Track%20AND%20artist:Some%20Artist"),
        ("Some Track", None, None, None),
    ],
)
def test_mb_get_track_search_query_str(
    valid_app_settings: AppSettings,
    track_name: str,
    artist_mbid: str | None,
    artist_name: str | None,
    expected: str | None,
) -> None:
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle")
    mb_client._throttle.return_value = None
    actual = mb_client._get_track_search_query_str(
        human_readable_track_name=track_name, artist_mbid=artist_mbid, human_readable_artist_name=artist_name
    )
    assert actual == expected, f"Expected '{expected}', but got '{actual}'"


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize("is_lfm_rec", [False, True])
@pytest.mark.parametrize(
    "mock_mb_json_response_fixture_name, track_name, artist_mbid, artist_name, expected",
    [
        (  # test case 1
            "mock_musicbrainz_track_search_arid_json",
            "rushup i bank 12 M",
            "09292e4d-b7ad-476b-86d9-7806303ef8c3",
            "The Tuss",
            {"origin_release_mbid": "3b08749b-b63e-46d3-b693-e0736faf046f", "origin_release_name": "Rushup Edge"},
        ),
        (  # test case 2: full track info provided
            "mock_musicbrainz_track_search_arid_json",
            "rushup i bank 12 M",
            "09292e4d-b7ad-476b-86d9-7806303ef8c3",
            "The Tuss",
            {"origin_release_mbid": "3b08749b-b63e-46d3-b693-e0736faf046f", "origin_release_name": "Rushup Edge"},
        ),
        (  # test case 3: result from searching by artist name and not arid.
            "mock_musicbrainz_track_search_artist_name_json",
            "rushup i bank 12 M",
            None,
            "The Tuss",
            {"origin_release_mbid": "3b08749b-b63e-46d3-b693-e0736faf046f", "origin_release_name": "Rushup Edge"},
        ),
        (  # test case 4: mbid response has no release title in it, should return None
            "mock_musicbrainz_track_search_no_release_name_json",
            "rushup i bank 12 M",
            None,
            "The Tuss",
            None,
        ),
        (  # test case 5: json response triggers a KeyError, result should be None
            "mb_track_response_raise_key_error",
            "rushup i bank 12 M",
            "09292e4d-b7ad-476b-86d9-7806303ef8c3",
            "The Tuss",
            None,
        ),
        (  # test case 6: json response triggers an IndexError, result should be None
            "mb_track_response_raise_index_error",
            "rushup i bank 12 M",
            "09292e4d-b7ad-476b-86d9-7806303ef8c3",
            "The Tuss",
            None,
        ),
    ],
)
def test_request_release_details_for_track(
    httpx_mock: HTTPXMock,
    request: pytest.FixtureRequest,
    valid_app_settings: AppSettings,
    make_track_search_item: pytest.FixtureRequest,
    is_lfm_rec: bool,
    mock_mb_json_response_fixture_name: str,
    track_name: str,
    artist_mbid: str | None,
    artist_name: str,
    expected: dict[str, str | None] | None,
) -> None:
    mock_json_resp = request.getfixturevalue(mock_mb_json_response_fixture_name)
    httpx_mock.add_response(json=mock_json_resp)
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle")
    mb_client._throttle.return_value = None
    mock_si = make_track_search_item(is_lfm_rec=is_lfm_rec, artist=artist_name, track=track_name)
    actual = mb_client.request_release_details_for_track(si=mock_si, artist_mbid=artist_mbid)
    assert actual == expected, f"Expected {expected}, but got {actual}"


@pytest.mark.override_global_httpx_mock
def test_request_release_details_error_handling(httpx_mock: HTTPXMock, valid_app_settings: AppSettings) -> None:
    httpx_mock.add_response(status_code=404)
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle")
    mb_client._throttle.return_value = None
    with pytest.raises(
        MusicBrainzClientException, match=re.escape("Unexpected Musicbrainz API error encountered for URL ")
    ):
        mb_client.request_release_details(mbid="fake")


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize("is_lfm_rec", [False, True])
def test_request_release_details_for_track_error_handling(
    httpx_mock: HTTPXMock,
    valid_app_settings: AppSettings,
    make_track_search_item: pytest.FixtureRequest,
    is_lfm_rec: bool,
) -> None:
    httpx_mock.add_response(status_code=404)
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle")
    mb_client._throttle.return_value = None
    mock_si = make_track_search_item(is_lfm_rec=is_lfm_rec)
    actual = mb_client.request_release_details_for_track(si=mock_si, artist_mbid="a")
    assert actual is None


def test_request_release_details_for_track_api_error() -> None:
    pass  # TODO: implement
