from contextlib import nullcontext
from unittest.mock import Mock

import pytest
from pytest_httpx import HTTPXMock

from plastered.config.config_parser import AppConfig
from plastered.run_cache.run_cache import RunCache
from plastered.utils.exceptions import LFMClientException
from plastered.utils.httpx_utils.lfm_client import LFMAPIClient


@pytest.fixture(scope="session")
def expected_lfm_request_api_res_top_keys() -> dict[str, set[str]]:
    """
    Utility fixture which maps an LFM API endpoint to the expected set of top-level keys
    returned by the lfm_client.request_api call.
    """
    return {
        "album.getinfo": set(
            ["artist", "image", "listeners", "mbid", "name", "playcount", "tags", "tracks", "url", "wiki"]
        ),
        "track.getinfo": set(
            ["album", "artist", "duration", "listeners", "mbid", "name", "playcount", "streamable", "toptags", "url"]
        ),
    }


@pytest.mark.parametrize(
    "method, should_fail",
    [("album.getinfo", False), ("track.getinfo", False), ("album.search", True), ("fake.method", True)],
)
def test_request_lfm_api(
    disabled_api_run_cache: RunCache,
    valid_app_settings: AppConfig,
    expected_lfm_request_api_res_top_keys: dict[str, set[str]],
    method: str,
    should_fail: bool,
) -> None:
    expected_throttle_call_cnt = 0 if should_fail else 1
    lfm_client = LFMAPIClient(app_settings=valid_app_settings, run_cache=disabled_api_run_cache)
    lfm_client._throttle = Mock(name="_throttle")
    lfm_client._throttle.return_value = None
    with pytest.raises(ValueError, match="Invalid endpoint*") if should_fail else nullcontext():
        result = lfm_client.request_api(method=method, params="fakekey=fakevalue")
        len(lfm_client._throttle.mock_calls) == expected_throttle_call_cnt
    if not should_fail:
        assert isinstance(result, dict), f"Expected request_lfm_api result type of dict, but found: {type(result)}"
        assert set(result.keys()) == expected_lfm_request_api_res_top_keys[method]


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize("method", ["album.getinfo", "track.getinfo"])
def test_request_lfm_api_non_200_status(
    httpx_mock: HTTPXMock, disabled_api_run_cache: RunCache, valid_app_settings: AppConfig, method: str
) -> None:
    httpx_mock.add_response(status_code=404)
    lfm_client = LFMAPIClient(app_settings=valid_app_settings, run_cache=disabled_api_run_cache)
    lfm_client._throttle = Mock(name="_throttle")
    lfm_client._throttle.return_value = None
    with pytest.raises(LFMClientException, match=f"Unexpected LFM API error encountered for method '{method}'"):
        result = lfm_client.request_api(method=method, params="fakekey=fakevalue")
        lfm_client._throttle.assert_called_once()


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize("method", ["album.getinfo", "track.getinfo"])
def test_request_lfm_api_bad_json_response(
    httpx_mock: HTTPXMock, disabled_api_run_cache: RunCache, valid_app_settings: AppConfig, method: str
) -> None:
    httpx_mock.add_response(
        status_code=200, json={"error": 123, "message": "LFM API handles errors like this sometimes"}
    )
    lfm_client = LFMAPIClient(app_settings=valid_app_settings, run_cache=disabled_api_run_cache)
    lfm_client._throttle = Mock(name="_throttle")
    lfm_client._throttle.return_value = None
    with pytest.raises(LFMClientException, match="LFM API error encounterd. LFM error code: '123'"):
        lfm_client.request_api(method=method, params="fakekey=fakevalue")


@pytest.mark.override_global_httpx_mock
def test_api_client_cache_hit(
    httpx_mock: HTTPXMock, enabled_api_run_cache: RunCache, valid_app_settings: AppConfig
) -> None:
    endpoint = "album.getinfo"
    params = "lfmcachechecking&a=b"
    mocked_json = {"album": {"cache_hit": "hopefully"}}
    test_client = LFMAPIClient(app_settings=valid_app_settings, run_cache=enabled_api_run_cache)
    expected_cache_key = (test_client._base_domain, endpoint, params)
    enabled_api_run_cache._cache.set(expected_cache_key, mocked_json, expire=3600)
    actual_result = test_client.request_api(endpoint, params)
    assert actual_result == mocked_json
    assert not httpx_mock.get_requests()
