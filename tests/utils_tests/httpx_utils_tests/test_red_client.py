from contextlib import nullcontext
from unittest.mock import Mock

import pytest
from pytest_httpx import HTTPXMock

from plastered.config.config_parser import AppConfig
from plastered.run_cache.run_cache import RunCache
from plastered.utils.httpx_utils.red_client import RedAPIClient


@pytest.mark.httpx_mock(assert_all_requests_were_expected=False)
@pytest.mark.parametrize(
    "action, expected_top_keys, should_fail",
    [
        ("browse", set(["currentPage", "pages", "results"]), False),
        ("torrentgroup", set(["group", "torrents"]), False),
        (
            "community_stats",
            set(
                [
                    "downloaded",
                    "leeching",
                    "seeding",
                    "seedingperc",
                    "seedingsize",
                    "snatched",
                    "udownloaded",
                    "usnatched",
                ]
            ),
            False,
        ),
        ("user_torrents", set(["seeding"]), False),
        (
            "usersearch",
            set(
                [
                    "avatar",
                    "bbProfileText",
                    "community",
                    "isFriend",
                    "personal",
                    "profileAlbum",
                    "profileText",
                    "ranks",
                    "stats",
                    "username",
                ]
            ),
            True,
        ),
        ("somefakeaction", set(), True),
        ("download", set(), True),
    ],
)
def test_request_red_api(
    disabled_api_run_cache: RunCache,
    valid_app_config: AppConfig,
    action: str,
    expected_top_keys: set[str] | None,
    should_fail: bool,
) -> None:
    expected_throttle_call_cnt = 0 if should_fail else 1
    red_client = RedAPIClient(app_config=valid_app_config, run_cache=disabled_api_run_cache)
    red_client._throttle = Mock(name="_throttle")
    red_client._throttle.return_value = None
    with pytest.raises(ValueError, match="Invalid endpoint*") if should_fail else nullcontext():
        result = red_client.request_api(action=action, params="fakekey=fakevalue")
        actual_throttle_call_cnt = len(red_client._throttle.mock_calls)
        assert actual_throttle_call_cnt == expected_throttle_call_cnt
    if not should_fail:
        assert isinstance(result, dict), f"Expected result type to be a dict, but got: {type(result)}"
        assert set(result.keys()) == expected_top_keys, f"Unexpected top-level JSON keys in response."


@pytest.mark.override_global_httpx_mock
def test_red_client_cache_hit(
    httpx_mock: HTTPXMock, enabled_api_run_cache: RunCache, valid_app_config: AppConfig
) -> None:
    endpoint = "browse"
    params = "fake-cache-check=test&foo=bar"
    mocked_json = {"response": {"cache_hit": "hopefully"}}
    test_client = RedAPIClient(app_config=valid_app_config, run_cache=enabled_api_run_cache)
    expected_cache_key = (test_client._base_domain, endpoint, params)
    enabled_api_run_cache._cache.set(expected_cache_key, mocked_json, expire=3600)
    actual_result = test_client.request_api(endpoint, params)
    assert actual_result == mocked_json
    assert not httpx_mock.get_requests()
