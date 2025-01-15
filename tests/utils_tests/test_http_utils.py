import datetime
from typing import Any, Callable, Dict, List, Optional, Set
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from plastered.config.config_parser import AppConfig
from plastered.run_cache.run_cache import CacheType, RunCache
from plastered.utils.exceptions import RedClientSnatchException
from plastered.utils.http_utils import (
    LFMAPIClient,
    MusicBrainzAPIClient,
    RedAPIClient,
    ThrottledAPIBaseClient,
)
from tests.conftest import (
    api_run_cache,
    mock_lfm_session_get_side_effect,
    mock_mb_session_get_side_effect,
    mock_red_session_get_side_effect,
    mock_red_snatch_get_side_effect,
    valid_app_config,
)

# @pytest.fixture(scope="", autouse=True)
# def default_noop_requests_session_get_mock():
#     with patch("requests.Session.get", return_value=None) as mock_sesh_get_fixture:
#         yield mock_sesh_get_fixture


def _subclass_to_side_effect_fn(subclass_name: str) -> Callable:
    return {
        "LFMAPIClient": mock_lfm_session_get_side_effect,
        "MusicBrainzAPIClient": mock_mb_session_get_side_effect,
        "RedAPIClient": mock_red_session_get_side_effect,
    }[subclass_name]


@pytest.fixture(scope="session")
def api_client_to_app_config_keys() -> Dict[str, Dict[str, str]]:
    """
    Utility fixture that returns a mapping of the name of each ThrottledAPIBaseClient subclass,
    to a subdict which maps from the standard attribute type to the specific CLI option in the AppConfig.
    """
    return {
        "RedAPIClient": {
            "retries": "red_api_retries",
            "period": "red_api_seconds_between_calls",
            "key": "red_api_key",
        },
        "LFMAPIClient": {
            "retries": "lfm_api_retries",
            "period": "lfm_api_seconds_between_calls",
            "key": "red_api_key",
        },
        "MusicBrainzAPIClient": {
            "retries": "musicbrainz_api_max_retries",
            "period": "musicbrainz_api_seconds_between_calls",
        },
    }


@pytest.mark.parametrize(
    "client_throttle_sec, dt_now_call_timestamps, expected_sleep_call_args",
    [
        (  # CASE 1: all throttle calls are precisely spaced the throttle period. Expect no sleep calls
            5,
            [
                datetime.datetime.fromtimestamp(1512345000),  # start ts
                datetime.datetime.fromtimestamp(1512345000),  # initial call not blocked
                datetime.datetime.fromtimestamp(1512345005),  # +5s
                datetime.datetime.fromtimestamp(1512345005),  # call not blocked
                datetime.datetime.fromtimestamp(1512345010),  # +5s
                datetime.datetime.fromtimestamp(1512345010),  # call not blocked
            ],
            [],
        ),
        (  # CASE 2: all throttle calls are spaced more than the throttle period. Expect no sleep calls
            3,
            [
                datetime.datetime.fromtimestamp(1512345000),  # start ts
                datetime.datetime.fromtimestamp(1512345000),  # initial call not blocked
                datetime.datetime.fromtimestamp(1512345010),  # +10s
                datetime.datetime.fromtimestamp(1512345010),  # call not blocked
                datetime.datetime.fromtimestamp(1512345016),  # +6s
                datetime.datetime.fromtimestamp(1512345016),  # call not blocked
            ],
            [],
        ),
        (  # CASE 3: 2 throttle calls are earlier than the period allows. Expect two sleep calls
            2,
            [
                datetime.datetime.fromtimestamp(1736087000),  # start ts
                datetime.datetime.fromtimestamp(1736087000),  # initial call not blocked
                datetime.datetime.fromtimestamp(1736087003),  # +3s
                datetime.datetime.fromtimestamp(1736087003),  # call not blocked
                datetime.datetime.fromtimestamp(1736087004),  # +1s
                datetime.datetime.fromtimestamp(1736087005),  # call blocked 1s (post-sleep call)
                datetime.datetime.fromtimestamp(1736087008),  # +3s
                datetime.datetime.fromtimestamp(1736087008),  # call not blocked
                datetime.datetime.fromtimestamp(1736087008),  # +0s
                datetime.datetime.fromtimestamp(1736087010),  # call blocked 2s (post-sleep call)
            ],
            [1, 2],
        ),
        (  # CASE 4: All throttle calls after initial call are earlier than the period allows. Expect 3 sleep calls
            2,
            [
                datetime.datetime.fromtimestamp(1736087000),  # start ts
                datetime.datetime.fromtimestamp(1736087000),  # initial call not blocked
                datetime.datetime.fromtimestamp(1736087001),  # +1s
                datetime.datetime.fromtimestamp(1736087002),  # call blocked 1s (post-sleep call)
                datetime.datetime.fromtimestamp(1736087002),  # +0s
                datetime.datetime.fromtimestamp(1736087004),  # call blocked 2s (post-sleep call)
                datetime.datetime.fromtimestamp(1736087005),  # +1s
                datetime.datetime.fromtimestamp(1736087006),  # call blocked 1s (post-sleep call)
            ],
            [1, 2, 1],
        ),
    ],
)
def test_throttle(
    api_run_cache: RunCache,
    client_throttle_sec: int,
    dt_now_call_timestamps: List[datetime.datetime],
    expected_sleep_call_args: List[int],
) -> None:
    api_base_client = ThrottledAPIBaseClient(
        base_api_url="google.com",
        max_api_call_retries=3,
        seconds_between_api_calls=client_throttle_sec,
        valid_endpoints=set(["fake-endpoint1", "fake-endpoint-2"]),
        run_cache=api_run_cache,
    )
    api_base_client._time_of_last_call = dt_now_call_timestamps[0] - datetime.timedelta(hours=1)
    expected_num_throttle_calls = len(dt_now_call_timestamps) // 2
    expected_datetime_now_call_cnt = len(dt_now_call_timestamps)
    # NOTE: mocking datetime is funky. Had to follow this advice: https://stackoverflow.com/a/70598060
    with patch("plastered.utils.http_utils.datetime", wraps=datetime.datetime) as mock_dt:
        mock_dt.now.side_effect = dt_now_call_timestamps
        with patch("plastered.utils.http_utils.sleep") as mock_sleep:
            mock_sleep.return_value = None
            assert api_base_client._throttle_period == datetime.timedelta(seconds=client_throttle_sec)
            for i in range(expected_num_throttle_calls):
                api_base_client._throttle()
            mock_sleep.assert_has_calls([call.sleep(expected_arg) for expected_arg in expected_sleep_call_args])
            mock_dt.assert_has_calls([call.now() for _ in range(expected_datetime_now_call_cnt)])


@pytest.mark.parametrize(
    "subclass, endpoint, params, expected",
    [
        (RedAPIClient, "browse", "&something=otherthing", True),
        (LFMAPIClient, "album.getinfo", "&something=otherthing", True),
        (MusicBrainzAPIClient, "release", "&mbid=69420", True),
    ],
)
def test_throttled_api_client_write_cache_valid(
    valid_app_config: AppConfig,
    api_run_cache: RunCache,
    subclass: ThrottledAPIBaseClient,
    endpoint: str,
    params: str,
    expected: bool,
) -> None:
    cur_side_effect = _subclass_to_side_effect_fn(subclass_name=subclass.__name__)
    with patch("requests.Session.get", side_effect=cur_side_effect) as mock_sesh_get:
        with patch.object(RunCache, "write_data") as mock_run_cache_write_method:
            mock_run_cache_write_method.return_value = True
            test_client = subclass(app_config=valid_app_config, run_cache=api_run_cache)
            actual = test_client._write_cache_if_enabled(
                endpoint=endpoint, params=params, result_json={"fake": "value"}
            )
            expected_cache_key = (test_client._base_domain, endpoint, params)
            mock_run_cache_write_method.assert_called_once_with(cache_key=expected_cache_key, data={"fake": "value"})
            assert actual == True


@pytest.mark.parametrize(
    "subclass, cache_enabled, endpoint, params",
    [
        (RedAPIClient, False, "browse", "&something=otherthing"),
        (RedAPIClient, True, "download", "&id=blah"),
        (RedAPIClient, True, "community_stats", "&non-cached-endpoint=nothing&no=cache"),
        (RedAPIClient, True, "user_torrents", "&non-cached-endpoint=nothing&no=cache"),
        (LFMAPIClient, False, "album.getinfo", "&something=otherthing"),
        (MusicBrainzAPIClient, False, "release", "&something=otherthing"),
    ],
)
def test_throttled_api_client_write_cache_not_valid(
    valid_app_config: AppConfig,
    api_run_cache: RunCache,
    subclass: ThrottledAPIBaseClient,
    cache_enabled: bool,
    endpoint: str,
    params: str,
) -> None:
    cur_side_effect = _subclass_to_side_effect_fn(subclass_name=subclass.__name__)
    with patch("requests.Session.get", side_effect=cur_side_effect) as mock_sesh_get:
        with patch.object(RunCache, "write_data") as mock_run_cache_write_method:
            with patch.object(RunCache, "write_data") as mock_run_cache_enabled:
                mock_run_cache_write_method.return_value = None
                mock_run_cache_enabled.return_value = cache_enabled
                test_client = subclass(app_config=valid_app_config, run_cache=api_run_cache)
                actual = test_client._write_cache_if_enabled(
                    endpoint=endpoint, params=params, result_json={"fake": "value"}
                )
                mock_run_cache_write_method.assert_not_called()
                assert actual == False


@pytest.mark.parametrize(
    "subclass, expected_base_domain",
    [
        (RedAPIClient, "redacted.sh"),
        (LFMAPIClient, "ws.audioscrobbler.com"),
        (MusicBrainzAPIClient, "musicbrainz.org"),
    ],
)
def test_init_throttled_api_client(
    api_run_cache: RunCache,
    valid_app_config: AppConfig,
    subclass: ThrottledAPIBaseClient,
    expected_base_domain: str,
    api_client_to_app_config_keys: Dict[str, Dict[str, str]],
) -> None:
    test_instance = subclass(app_config=valid_app_config, run_cache=api_run_cache)
    assert issubclass(test_instance.__class__, ThrottledAPIBaseClient)
    actual_base_domain = test_instance._base_domain
    assert (
        actual_base_domain == expected_base_domain
    ), f"Expected base domain to be '{expected_base_domain}', but got '{actual_base_domain}'"
    app_config_keys = api_client_to_app_config_keys[test_instance.__class__.__name__]
    expected_max_retries = valid_app_config.get_cli_option(app_config_keys["retries"])
    expected_throttle_period = datetime.timedelta(seconds=valid_app_config.get_cli_option(app_config_keys["period"]))
    actual_max_retries = test_instance._max_api_call_retries
    assert (
        actual_max_retries == expected_max_retries
    ), f"Expected max retries to be {expected_max_retries}, but got {actual_max_retries}"
    actual_throttle_period = test_instance._throttle_period
    assert (
        actual_throttle_period == expected_throttle_period
    ), f"Expected throttle period to be {expected_throttle_period}, but got {actual_throttle_period}"


@pytest.mark.parametrize(
    "action, expected_top_keys, should_fail, exception_type, exception_message",
    [
        ("browse", set(["currentPage", "pages", "results"]), False, None, None),
        ("usersearch", set(), True, ValueError, "Invalid endpoint*"),
        ("somefakeaction", set(), True, ValueError, "Invalid endpoint*"),
        ("download", None, True, ValueError, "Invalid endpoint*"),
    ],
)
def test_request_red_api(
    api_run_cache: RunCache,
    valid_app_config: AppConfig,
    action: str,
    expected_top_keys: Optional[Set[str]],
    should_fail: bool,
    exception_type: Optional[Exception],
    exception_message: Optional[str],
) -> None:
    with patch("requests.Session.get", side_effect=mock_red_session_get_side_effect) as mock_sesh_get:
        red_client = RedAPIClient(app_config=valid_app_config, run_cache=api_run_cache)
        red_client._throttle = Mock(name="_throttle")
        red_client._throttle.return_value = None
        if should_fail:
            with pytest.raises(exception_type, match=exception_message):
                result = red_client.request_api(action=action, params="fakekey=fakevalue")
                mock_sesh_get.assert_not_called()
                red_client._throttle.assert_not_called()
            return
        result = red_client.request_api(action=action, params="fakekey=fakevalue&someotherkey=someothervalue")
        red_client._throttle.assert_called_once()
        if action == "download":
            assert result is not None
        else:
            mock_sesh_get.assert_called_once_with(
                url=f"https://redacted.sh/ajax.php?action={action}&fakekey=fakevalue&someotherkey=someothervalue"
            )
            assert isinstance(result, dict), f"Expected result type to be a dict, but got: {type(result)}"
            assert set(result.keys()) == expected_top_keys, f"Unexpected top-level JSON keys in response."


@pytest.mark.parametrize("mock_status_code_val, should_raise_exception", [(200, False), (404, True)])
def test_snatch_red_api_no_fl(
    api_run_cache: RunCache,
    valid_app_config: AppConfig,
    mock_status_code_val: int,
    should_raise_exception: bool,
) -> None:
    with patch("requests.Session.get", return_value=MagicMock(status_code=mock_status_code_val)) as mock_sesh_get:
        red_client = RedAPIClient(app_config=valid_app_config, run_cache=api_run_cache)
        red_client._throttle = Mock(name="_throttle")
        red_client._throttle.return_value = None
        if should_raise_exception:
            with pytest.raises(RedClientSnatchException):
                result = red_client.snatch(tid="69", can_use_token_on_torrent=False)
                red_client._throttle.assert_called_once()
                mock_sesh_get.assert_called_once()
        else:
            result = red_client.snatch(tid="69", can_use_token_on_torrent=False)
            mock_sesh_get.assert_called_once()
            red_client._throttle.assert_called_once()


@pytest.mark.parametrize(
    "mock_response_list, expected_throttle_calls, expected_get_calls, expected_exception",
    [
        (
            [MagicMock(status_code=200, content=bytes("fake", encoding="utf-8"))],
            1,
            [call(url="https://redacted.sh/ajax.php?action=download&id=69&usetoken=1")],
            None,
        ),
        (
            [
                MagicMock(status_code=404, content=bytes("fake", encoding="utf-8")),
                MagicMock(status_code=200, content=bytes("another-fake", encoding="utf-8")),
            ],
            2,
            [
                call(url="https://redacted.sh/ajax.php?action=download&id=69&usetoken=1"),
                call(url="https://redacted.sh/ajax.php?action=download&id=69"),
            ],
            None,
        ),
        (
            [
                MagicMock(status_code=404, content=bytes("fake", encoding="utf-8")),
                MagicMock(status_code=404, content=bytes("another-fake", encoding="utf-8")),
            ],
            2,
            [
                call(url="https://redacted.sh/ajax.php?action=download&id=69&usetoken=1"),
                call(url="https://redacted.sh/ajax.php?action=download&id=69"),
            ],
            RedClientSnatchException,
        ),
        (
            [lambda x: x / 0, MagicMock(status_code=200, content=bytes("another-fake", encoding="utf-8"))],
            2,
            [
                call(url="https://redacted.sh/ajax.php?action=download&id=69&usetoken=1"),
                call(url="https://redacted.sh/ajax.php?action=download&id=69"),
            ],
            None,
        ),
    ],
)
def test_snatch_red_api_use_token(
    api_run_cache: RunCache,
    valid_app_config: AppConfig,
    mock_response_list: List[MagicMock],
    expected_throttle_calls: int,
    expected_get_calls: List[Callable],
    expected_exception: Optional[Exception],
) -> None:
    with patch("requests.Session.get") as mock_sesh_get:
        mock_sesh_get.side_effect = mock_response_list
        red_client = RedAPIClient(app_config=valid_app_config, run_cache=api_run_cache)
        red_client._use_fl_tokens = True
        red_client._throttle = Mock(name="_throttle")
        red_client._throttle.return_value = None
        if expected_exception:
            with pytest.raises(expected_exception):
                result = red_client.snatch(tid="69", can_use_token_on_torrent=True)
        else:
            result = red_client.snatch(tid="69", can_use_token_on_torrent=True)
        mock_sesh_get.assert_has_calls(expected_get_calls)
        actual_throttle_calls = len(red_client._throttle.mock_calls)
        assert (
            actual_throttle_calls == expected_throttle_calls
        ), f"Expected {expected_throttle_calls}, but found {actual_throttle_calls}"


@pytest.mark.parametrize(
    "method, expected_top_keys, should_fail, exception_type, exception_message",
    [
        (
            "album.getinfo",
            set(["artist", "image", "listeners", "mbid", "name", "playcount", "tags", "tracks", "url", "wiki"]),
            False,
            None,
            None,
        ),
        (
            "track.getinfo",
            set(
                [
                    "album",
                    "artist",
                    "duration",
                    "listeners",
                    "mbid",
                    "name",
                    "playcount",
                    "streamable",
                    "toptags",
                    "url",
                ]
            ),
            False,
            None,
            None,
        ),
        ("album.search", set(), True, ValueError, "Invalid endpoint*"),
        ("fake.method", set(), True, ValueError, "Invalid endpoint*"),
    ],
)
def test_request_lfm_api(
    api_run_cache: RunCache,
    valid_app_config: AppConfig,
    method: str,
    expected_top_keys: Set[str],
    should_fail: bool,
    exception_type: Optional[Exception],
    exception_message: Optional[str],
) -> None:
    with patch("requests.Session.get", side_effect=mock_lfm_session_get_side_effect) as mock_sesh_get:
        lfm_client = LFMAPIClient(app_config=valid_app_config, run_cache=api_run_cache)
        lfm_client._throttle = Mock(name="_throttle")
        lfm_client._throttle.return_value = None
        if should_fail:
            with pytest.raises(exception_type, match=exception_message):
                result = lfm_client.request_api(method=method, params="fakekey=fakevalue")
                lfm_client._throttle.assert_not_called()
        else:
            result = lfm_client.request_api(method=method, params="fakekey=val&other=bla")
            lfm_client._throttle.assert_called_once()
            assert isinstance(
                result, dict
            ), f"Expected result from request_lfm_api to be of type dict, but was of type: {type(result)}"
            assert expected_top_keys == set(
                result.keys()
            ), f"Unexpected mismatch in top-level JSON keys for request_lfm_api response."


@pytest.mark.parametrize(
    "entity_type, expected_mbid, should_fail, exception_type, exception_message",
    [
        ("release", "d211379d-3203-47ed-a0c5-e564815bb45a", False, None, None),
        (
            "release-group",
            "d211379d-3203-47ed-a0c5-e564815bb45a",
            True,
            ValueError,
            "Invalid endpoint*",
        ),
        (
            "album",
            "some-fake-mbid-here",
            True,
            ValueError,
            "Invalid endpoint*",
        ),
        (
            "song",
            "some-other-fake-mbid-here",
            True,
            ValueError,
            "Invalid endpoint*",
        ),
    ],
)
def test_request_musicbrainz_api(
    valid_app_config: AppConfig,
    api_run_cache: RunCache,
    entity_type: str,
    expected_mbid: str,
    should_fail: bool,
    exception_type: Optional[Exception],
    exception_message: Optional[str],
) -> None:
    with patch("requests.Session.get", side_effect=mock_mb_session_get_side_effect) as mock_sesh_get:
        mb_client = MusicBrainzAPIClient(app_config=valid_app_config, run_cache=api_run_cache)
        mb_client._throttle = Mock(name="_throttle")
        mb_client._throttle.return_value = None
        if should_fail:
            with pytest.raises(exception_type, match=exception_message):
                result = mb_client.request_api(entity_type=entity_type, mbid=expected_mbid)
                mb_client._throttle.assert_not_called()
        else:
            result = mb_client.request_api(entity_type="release", mbid=expected_mbid)
            mb_client._throttle.assert_called_once()
            assert isinstance(result, dict), f"Expected result from request_api to be a dict, but was: {type(result)}"
            assert "id" in result.keys(), f"Missing expected top-level key in musicbrainz response: 'id'"
            response_mbid = result["id"]
            assert (
                response_mbid == expected_mbid
            ), f"Mismatch between actual response mbid ('{response_mbid}') and expected mbid ('{expected_mbid}')"


@pytest.mark.parametrize(
    "subclass, expected_base_domain, endpoint, params, mocked_json",
    [
        (
            RedAPIClient,
            "redacted.sh",
            "browse",
            "&some-fake-cache-check=testing&foo=blah",
            {"response": {"cache_hit": "hopefully"}},
        ),
        (
            LFMAPIClient,
            "ws.audioscrobbler.com",
            "album.getinfo",
            "&lfmcachechecking&fun=ion",
            {"album": {"cache_hit": "hopefully"}},
        ),
        (
            MusicBrainzAPIClient,
            "musicbrainz.org",
            "release",
            "&mbid=69420&blah=not",
            {"musicbrainz-deeznuts": {"cache_hit": "hopefully"}},
        ),
    ],
)
def test_api_client_cache_hit(
    api_run_cache: RunCache,
    valid_app_config: AppConfig,
    subclass: ThrottledAPIBaseClient,
    expected_base_domain: str,
    endpoint: str,
    params: str,
    mocked_json: Dict[str, Any],
) -> None:
    cur_side_effect = _subclass_to_side_effect_fn(subclass_name=subclass.__name__)
    with patch("requests.Session.get", side_effect=cur_side_effect) as mock_sesh_get:
        test_client = subclass(app_config=valid_app_config, run_cache=api_run_cache)
        expected_cache_key = (expected_base_domain, endpoint, params)
        api_run_cache._cache.set(expected_cache_key, mocked_json, expire=3600)
        actual_result = test_client.request_api(endpoint, params)
        assert actual_result == mocked_json
        mock_sesh_get.assert_not_called()
