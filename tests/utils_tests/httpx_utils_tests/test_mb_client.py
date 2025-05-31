from typing import Any, Dict, Optional
from unittest.mock import Mock

import pytest
from pytest_httpx import HTTPXMock

from plastered.config.config_parser import AppConfig
from plastered.run_cache.run_cache import RunCache
from plastered.utils.httpx_utils import MusicBrainzAPIClient


@pytest.fixture(scope="session")
def mb_track_response_raise_index_error() -> Dict[str, Any]:
    return {"recordings": []}


@pytest.fixture(scope="session")
def mb_track_response_raise_key_error() -> Dict[str, Any]:
    return {"recordings": [{"missing_releases_key": True}]}


@pytest.mark.parametrize("expected_mbid", ["d211379d-3203-47ed-a0c5-e564815bb45a"])
def test_request_musicbrainz_api(
    valid_app_config: AppConfig,
    disabled_api_run_cache: RunCache,
    expected_mbid: str,
) -> None:
    mb_client = MusicBrainzAPIClient(app_config=valid_app_config, run_cache=disabled_api_run_cache)
    mb_client._throttle = Mock(name="_throttle")
    mb_client._throttle.return_value = None
    result = mb_client.request_release_details(mbid=expected_mbid)
    mb_client._throttle.assert_called_once()
    assert isinstance(result, dict), f"Expected result from request_api to be a dict, but was: {type(result)}"
    assert "id" in result.keys(), f"Missing expected top-level key in musicbrainz response: 'id'"
    response_mbid = result["id"]
    assert (
        response_mbid == expected_mbid
    ), f"Mismatch between actual response mbid ('{response_mbid}') and expected mbid ('{expected_mbid}')"


@pytest.mark.parametrize(
    "track_name, artist_mbid, artist_name, expected",
    [
        ("Some Track", "69-420abc", "Some Artist", "recording:Some%20Track%20AND%20arid:69-420abc"),
        ("Some Track", None, "Some Artist", "recording:Some%20Track%20AND%20artist:Some%20Artist"),
        ("Some Track", None, None, None),
    ],
)
def test_mb_get_track_search_query_str(
    valid_app_config: AppConfig,
    disabled_api_run_cache: RunCache,
    track_name: str,
    artist_mbid: Optional[str],
    artist_name: Optional[str],
    expected: Optional[str],
) -> None:
    mb_client = MusicBrainzAPIClient(app_config=valid_app_config, run_cache=disabled_api_run_cache)
    mb_client._throttle = Mock(name="_throttle")
    mb_client._throttle.return_value = None
    actual = mb_client._get_track_search_query_str(
        human_readable_track_name=track_name,
        artist_mbid=artist_mbid,
        human_readable_artist_name=artist_name,
    )
    assert actual == expected, f"Expected '{expected}', but got '{actual}'"


@pytest.mark.override_global_httpx_mock
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
        (  # test case 5: empty arid and artist name leading to nonetype result.
            "mock_musicbrainz_track_search_artist_name_json",
            "rushup i bank 12 M",
            None,
            None,
            None,
        ),
        (  # test case 6: json response triggers a KeyError, result should be None
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
        # ("mock_musicbrainz_track_search_artist_name_json"),
    ],
)
def test_request_release_details_for_track(
    httpx_mock: HTTPXMock,
    request: pytest.FixtureRequest,
    valid_app_config: AppConfig,
    disabled_api_run_cache: RunCache,
    mock_mb_json_response_fixture_name: str,
    track_name: str,
    artist_mbid: Optional[str],
    artist_name: Optional[str],
    expected: Optional[Dict[str, Optional[str]]],
) -> None:
    mock_json_resp = request.getfixturevalue(mock_mb_json_response_fixture_name)
    httpx_mock.add_response(json=mock_json_resp)
    mb_client = MusicBrainzAPIClient(app_config=valid_app_config, run_cache=disabled_api_run_cache)
    mb_client._throttle = Mock(name="_throttle")
    mb_client._throttle.return_value = None
    actual = mb_client.request_release_details_for_track(
        human_readable_track_name=track_name,
        artist_mbid=artist_mbid,
        human_readable_artist_name=artist_name,
    )
    assert actual == expected, f"Expected {expected}, but got {actual}"


@pytest.mark.parametrize(
    "track_name, artist_mbid, artist_name, expected_cache_val",
    [
        (  # test case 1: full track info provided
            "rushup i bank 12 M",
            "09292e4d-b7ad-476b-86d9-7806303ef8c3",
            "The Tuss",
            {"origin_release_mbid": "3b08749b-b63e-46d3-b693-e0736faf046f", "origin_release_name": "Rushup Edge"},
        ),
        (  # test case 2: result from searching by artist name and not arid.
            "rushup i bank 12 M",
            None,
            "The Tuss",
            {"origin_release_mbid": "3b08749b-b63e-46d3-b693-e0736faf046f", "origin_release_name": "Rushup Edge"},
        ),
    ],
)
def test_request_release_details_for_track_cache_hit(
    valid_app_config: AppConfig,
    enabled_api_run_cache: RunCache,
    track_name: str,
    artist_mbid: Optional[str],
    artist_name: Optional[str],
    expected_cache_val: Optional[Dict[str, Optional[str]]],
) -> None:
    mb_client = MusicBrainzAPIClient(app_config=valid_app_config, run_cache=enabled_api_run_cache)
    query_params = mb_client._get_track_search_query_str(
        human_readable_track_name=track_name,
        artist_mbid=artist_mbid,
        human_readable_artist_name=artist_name,
    )
    mb_client._throttle = Mock(name="_throttle")
    mb_client._throttle.return_value = None
    mb_client._write_cache_if_enabled(endpoint="recording", params=query_params, result_json=expected_cache_val)
    mb_client.request_release_details_for_track(
        human_readable_track_name=track_name,
        artist_mbid=artist_mbid,
        human_readable_artist_name=artist_name,
    )
    mb_client._throttle.assert_not_called()


@pytest.mark.override_global_httpx_mock
def test_mb_client_cache_hit(
    httpx_mock: HTTPXMock,
    enabled_api_run_cache: RunCache,
    valid_app_config: AppConfig,
) -> None:
    params = "fake-mbid-123"
    mocked_json = {"musicbrainz-deeznuts": {"cache_hit": "hopefully"}}
    test_client = MusicBrainzAPIClient(app_config=valid_app_config, run_cache=enabled_api_run_cache)
    expected_cache_key = (test_client._base_domain, test_client._release_endpoint, params)
    enabled_api_run_cache._cache.set(expected_cache_key, mocked_json, expire=3600)
    actual_result = test_client.request_release_details(mbid=params)
    assert actual_result == mocked_json
    assert not httpx_mock.get_requests()
