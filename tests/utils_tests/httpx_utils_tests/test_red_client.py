from contextlib import nullcontext
import re
from typing import Any
from unittest.mock import ANY, MagicMock, Mock, call, patch

import pytest
from pytest_httpx import HTTPXMock

from plastered.config.app_settings import AppSettings
from plastered.models.red_models import RedUserDetails, ReleaseEntry
from plastered.models.types import RedReleaseType
from plastered.utils.exceptions import RedUserDetailsInitError
from plastered.utils.httpx_utils.red_client import RedAPIClient


@pytest.mark.httpx_mock(assert_all_requests_were_expected=False)
@pytest.mark.parametrize(
    "action, expected_top_keys",
    [
        ("browse", set(["currentPage", "pages", "results"])),
        ("torrentgroup", set(["group", "torrents"])),
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
        ),
        ("user_torrents", set(["seeding"])),
    ],
)
def test_request_red_api(valid_app_settings: AppSettings, action: str, expected_top_keys: set[str]) -> None:
    red_client = RedAPIClient(app_settings=valid_app_settings)
    red_client._throttle = Mock(name="_throttle")
    red_client._throttle.return_value = None
    result = red_client.request_api(action=action, params="fakekey=fakevalue")
    assert len(red_client._throttle.mock_calls) == 1
    assert isinstance(result, dict), f"Expected result type to be a dict, but got: {type(result)}"
    assert set(result.keys()) == expected_top_keys, "Unexpected top-level JSON keys in response."


def test_create_red_user_details(valid_app_settings: AppSettings) -> None:
    mock_snatch_cnt = 69
    mock_seed_cnt = 420
    mock_user_profile_json = {"personal": {"giftTokens": 69, "meritTokens": 420}}

    def _side_effect(action: str, type_: str | None = None, lim: int | None = None) -> Any:
        return {
            "community_stats": (mock_snatch_cnt, mock_seed_cnt),
            "user_torrents": [],
            "user": mock_user_profile_json,
        }[action]

    with patch.object(RedAPIClient, "_rud_helper", side_effect=_side_effect) as mock_rud_helper:
        test_client = RedAPIClient(app_settings=valid_app_settings)
        actual = test_client.get_red_user_details()
        assert isinstance(actual, RedUserDetails)

        mock_rud_helper.assert_has_calls(
            [
                call(action="community_stats"),
                call(action="user_torrents", type_="snatched", lim=mock_snatch_cnt),
                call(action="user_torrents", type_="seeding", lim=mock_seed_cnt),
                call(action="user"),
            ],
            any_order=True,
        )


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
    request: pytest.FixtureRequest,
    action: str,
    mock_resp_fixture_name: str,
    type_: str | None,
    lim: int | None,
) -> None:
    mock_resp = request.getfixturevalue(mock_resp_fixture_name)["response"]
    with patch.object(RedAPIClient, "request_api", return_value=mock_resp) as mock_req_api:
        test_client = RedAPIClient(app_settings=valid_app_settings)
        actual = test_client._rud_helper(action=action, type_=type_, lim=lim)
        assert actual is not None
        mock_req_api.assert_called_once_with(action=action, params=ANY)


def test_rud_helper_raises(valid_app_settings: AppSettings) -> None:
    def _side_effect(*args, **kwargs) -> Any:
        raise Exception("Intentional mock exception for testing")

    with patch.object(RedAPIClient, "request_api", side_effect=_side_effect):
        test_client = RedAPIClient(app_settings=valid_app_settings)
        with pytest.raises(RedUserDetailsInitError, match=re.escape("during RedUserDetails initialization")):
            _ = test_client._rud_helper(action="user_torrents", type_="snatched", lim=69)


def test_browse(valid_app_settings: AppSettings) -> None:
    mock_params = "fake=val&other_fake=other_val"
    with (
        patch.object(RedAPIClient, "request_api", return_value={"results": ["foo", "bar"]}) as mock_request_api,
        patch.object(
            ReleaseEntry,
            "from_torrent_search_json_blob",
            return_value=ReleaseEntry(69, "CD", False, RedReleaseType.ALBUM),
        ) as mock_from_torrent_json_blob,
    ):
        test_client = RedAPIClient(app_settings=valid_app_settings)
        actual = test_client.browse(request_params=mock_params)
        assert isinstance(actual, list)
        assert len(actual) == 2
        assert all([isinstance(elem, ReleaseEntry) for elem in actual])
        mock_request_api.assert_called_once_with(action="browse", params=mock_params)
