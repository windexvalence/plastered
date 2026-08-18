from contextlib import nullcontext
import re
from typing import Any
from unittest.mock import ANY, MagicMock, Mock, call, patch

import pytest

from plastered.config.app_settings import AppSettings
from plastered.models.red_models import RedUserDetails, ReleaseEntry
from plastered.models.types import RedReleaseType
from plastered.utils.exceptions import RedUserDetailsInitError
from plastered.utils.http_clients.red_client import RedAPIClient


@pytest.mark.parametrize(
    "action, expected_top_keys",
    [
        (
            "artist",
            set(
                [
                    "id",
                    "name",
                    "notificationsEnabled",
                    "hasBookmarked",
                    "image",
                    "body",
                    "vanityHouse",
                    "tags",
                    "torrentgroup",
                ]
            ),
        ),
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


def test_get_artist_release_groups(valid_app_settings: AppSettings) -> None:
    with (
        patch.object(
            RedAPIClient, "request_api", return_value={"id": 1, "torrentgroup": ["blob-a", "blob-b"]}
        ) as mock_request_api,
        patch.object(
            ReleaseEntry,
            "from_artist_torrent_group_json_blob",
            return_value=ReleaseEntry(group_id=69, group_name="Some Album", release_type=RedReleaseType.ALBUM),
        ),
    ):
        test_client = RedAPIClient(app_settings=valid_app_settings)
        actual = test_client.get_artist_release_groups(artist_name="Some Artist")
        assert isinstance(actual, list)
        assert len(actual) == 2
        assert all([isinstance(elem, ReleaseEntry) for elem in actual])
        # The artist name is URL-encoded into the request params.
        mock_request_api.assert_called_once_with(action="artist", params="artistname=Some+Artist")


def test_get_artist_release_groups_artist_not_found(valid_app_settings: AppSettings) -> None:
    """A RED failure payload (no top-level response key -> request_api KeyError) resolves to an empty listing."""
    with patch.object(RedAPIClient, "request_api", side_effect=KeyError("response")):
        test_client = RedAPIClient(app_settings=valid_app_settings)
        assert test_client.get_artist_release_groups(artist_name="No Such Artist") == []


@pytest.mark.override_global_httpx_mock
def test_request_api_missing_response_key_raises(httpx2_mock, valid_app_settings: AppSettings) -> None:
    httpx2_mock.route().respond(json={"status": "failure", "error": "failure"})
    test_client = RedAPIClient(app_settings=valid_app_settings)
    test_client._throttle = Mock(name="_throttle", return_value=None)
    with pytest.raises(KeyError, match="missing expected"):
        test_client.request_api(action="artist", params="artistname=Nobody")
