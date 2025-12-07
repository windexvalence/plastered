from contextlib import nullcontext
import re
from typing import Any
from unittest.mock import ANY, MagicMock, Mock, call, patch

import pytest
from pytest_httpx import HTTPXMock

from plastered.config.app_settings import AppSettings
from plastered.models.red_models import RedUserDetails
from plastered.run_cache.run_cache import RunCache
from plastered.utils.exceptions import RedUserDetailsInitError
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
    valid_app_settings: AppSettings,
    action: str,
    expected_top_keys: set[str] | None,
    should_fail: bool,
) -> None:
    expected_throttle_call_cnt = 0 if should_fail else 1
    red_client = RedAPIClient(app_settings=valid_app_settings, run_cache=disabled_api_run_cache)
    red_client._throttle = Mock(name="_throttle")
    red_client._throttle.return_value = None
    with pytest.raises(ValueError, match="Invalid endpoint*") if should_fail else nullcontext():
        result = red_client.request_api(action=action, params="fakekey=fakevalue")
        actual_throttle_call_cnt = len(red_client._throttle.mock_calls)
        assert actual_throttle_call_cnt == expected_throttle_call_cnt
    if not should_fail:
        assert isinstance(result, dict), f"Expected result type to be a dict, but got: {type(result)}"
        assert set(result.keys()) == expected_top_keys, "Unexpected top-level JSON keys in response."


@pytest.mark.override_global_httpx_mock
def test_red_client_cache_hit(
    httpx_mock: HTTPXMock, enabled_api_run_cache: RunCache, valid_app_settings: AppSettings
) -> None:
    endpoint = "browse"
    params = "fake-cache-check=test&foo=bar"
    mocked_json = {"response": {"cache_hit": "hopefully"}}
    test_client = RedAPIClient(app_settings=valid_app_settings, run_cache=enabled_api_run_cache)
    expected_cache_key = (test_client._base_domain, endpoint, params)
    enabled_api_run_cache._cache.set(expected_cache_key, mocked_json, expire=3600)
    actual_result = test_client.request_api(endpoint, params)
    assert actual_result == mocked_json
    assert not httpx_mock.get_requests()


def test_create_red_user_details(valid_app_settings: AppSettings, enabled_api_run_cache: RunCache) -> None:
    mock_snatch_cnt = 69
    mock_seed_cnt = 420
    mock_user_profile_json = {"personal": {"giftTokens": 69, "meritTokens": 420}}

    def _side_effect(action: str, type_: str | None = None, lim: int | None = None) -> Any:
        return {
            "community_stats": (mock_snatch_cnt, mock_seed_cnt),
            "user_torrents": [],
            "user": mock_user_profile_json,
        }[action]

    test_client = RedAPIClient(app_settings=valid_app_settings)
    with patch.object(test_client, "_rud_helper", side_effect=_side_effect) as mock_rud_helper:
        actual = test_client.create_red_user_details()
        assert isinstance(actual, RedUserDetails)
        # mock_rud_helper.assert_has_calls(
        #     [
        #         call(action="community_stats"),
        #         call(action="user_torrents", type_="snatched", lim=mock_snatch_cnt),
        #         call(action="user_torrents", type_="seeding", lim=mock_seed_cnt),
        #         call(action="user"),
        #     ]
        # )


@pytest.mark.parametrize("cache_enabled", [False, True])
@pytest.mark.parametrize(
    "action, mock_resp_fixture_name, type_, lim",
    [
        ("community_stats", "mock_red_user_stats_response", None, None),
        ("user_torrents", "mock_red_user_torrents_snatched_response", "snatched", 216),
        ("user_torrents", "mock_red_user_torrents_seeding_response", "seeding", 397),
        ("user", "mock_red_user_response", None, None),
    ],
)
def test_rud_helper(
    valid_app_settings: AppSettings,
    enabled_api_run_cache: RunCache,
    request: pytest.FixtureRequest,
    cache_enabled: bool,
    action: str,
    mock_resp_fixture_name: str,
    type_: str | None,
    lim: int | None,
) -> None:
    mock_resp = request.getfixturevalue(mock_resp_fixture_name)["response"]
    run_cache = enabled_api_run_cache if cache_enabled else None
    with patch.object(RedAPIClient, "request_api", return_value=mock_resp) as mock_req_api:
        test_client = RedAPIClient(app_settings=valid_app_settings, run_cache=run_cache)
        actual = test_client._rud_helper(action=action, type_=type_, lim=lim)
        assert actual is not None
        mock_req_api.assert_called_once_with(action=action, params=ANY)


@pytest.mark.parametrize("cache_enabled", [False, True])
def test_rud_helper_raises(
    valid_app_settings: AppSettings,
    enabled_api_run_cache: RunCache,
    request: pytest.FixtureRequest,
    cache_enabled: bool,
) -> None:
    run_cache = enabled_api_run_cache if cache_enabled else None

    def _side_effect(*args, **kwargs) -> Any:
        raise Exception("Intentional mock exception for testing")

    with patch.object(RedAPIClient, "request_api", side_effect=_side_effect) as mock_req_api:
        test_client = RedAPIClient(app_settings=valid_app_settings, run_cache=run_cache)
        with pytest.raises(RedUserDetailsInitError, match=re.escape("during RedUserDetails initialization")):
            _ = test_client._rud_helper(action="user_torrents", type_="snatched", lim=69)
