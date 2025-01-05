import datetime
from typing import Dict, List, Optional, Set
from unittest.mock import Mock, call, patch

import pytest

from lastfm_recs_scraper.config.config_parser import AppConfig
from lastfm_recs_scraper.utils.constants import (
    LAST_FM_API_BASE_URL,
    MUSICBRAINZ_API_BASE_URL,
    RED_API_BASE_URL,
)
from lastfm_recs_scraper.utils.http_utils import (
    LastFMAPIClient,
    MusicBrainzAPIClient,
    RedAPIClient,
    ThrottledAPIBaseClient,
)
from tests.conftest import (
    mock_last_fm_session_get_side_effect,
    mock_mb_session_get_side_effect,
    mock_red_session_get_side_effect,
    valid_app_config,
)


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
        "LastFMAPIClient": {
            "retries": "last_fm_api_retries",
            "period": "last_fm_api_seconds_between_calls",
            "key": "red_api_key",
        },
        "MusicBrainzAPIClient": {
            "retries": "musicbrainz_api_max_retries",
            "period": "musicbrainz_api_seconds_between_calls",
        },
    }


@pytest.mark.parametrize(
    "client_throttle_sec, dt_now_call_timestamps, mocked_time_of_last_call, expected_datetime_now_call_cnt, expected_sleep_call_args",
    [
        (  # CASE 1: all throttle calls are precisely spaced the throttle period. Expecte no sleep calls
            5,
            [
                datetime.datetime.fromtimestamp(1512345000),  # start ts
                datetime.datetime.fromtimestamp(1512345005),  # +5s
                datetime.datetime.fromtimestamp(1512345010),  # +5s
            ],
            [
                datetime.datetime.fromtimestamp(1512345000),  # start ts
                datetime.datetime.fromtimestamp(1512345005),  # +5s
                datetime.datetime.fromtimestamp(1512345010),  # +5s
            ],
            3,
            [],
        ),
        (  # CASE 2: all throttle calls are spaced more than the throttle period. Expecte no sleep calls
            3,
            [
                datetime.datetime.fromtimestamp(1512345000),  # start ts
                datetime.datetime.fromtimestamp(1512345010),  # +10s
                datetime.datetime.fromtimestamp(1512345016),  # +6s
            ],
            [
                datetime.datetime.fromtimestamp(1512345000),  # start ts
                datetime.datetime.fromtimestamp(1512345010),  # +10s
                datetime.datetime.fromtimestamp(1512345016),  # +6s
            ],
            3,
            [],
        ),
        (  # CASE 3: 2 throttle calls are earlier than the period allows. Expecte two sleep calls
            2,
            [
                datetime.datetime.fromtimestamp(1736087000),  # start ts
                datetime.datetime.fromtimestamp(1736087003),  # +3s
                datetime.datetime.fromtimestamp(1736087004),  # +1s
                datetime.datetime.fromtimestamp(1736087005),  # +1s (post-sleep call)
                datetime.datetime.fromtimestamp(1736087008),  # +4s
                datetime.datetime.fromtimestamp(1736087008),  # +0s
                datetime.datetime.fromtimestamp(1736087010),  # +2s (post-sleep call)
                datetime.datetime.fromtimestamp(1736087018),  # +10s
            ],
            [
                datetime.datetime.fromtimestamp(1736087000),  # start ts
                datetime.datetime.fromtimestamp(1736087003),  # +3s
                datetime.datetime.fromtimestamp(1736087005),  # +1s (post-sleep call)
                datetime.datetime.fromtimestamp(1736087008),  # +4s
                datetime.datetime.fromtimestamp(1736087010),  # +2s (post-sleep call)
                datetime.datetime.fromtimestamp(1736087018),  # +10s
            ],
            8,
            [1, 2],
        ),
        (  # CASE 4: All throttle calls after initial call are earlier than the period allows. Expect 3 sleep calls
            2,
            [
                datetime.datetime.fromtimestamp(1736087000),  # start ts
                datetime.datetime.fromtimestamp(1736087001),  # +1s
                datetime.datetime.fromtimestamp(1736087002),  # +1s (post-sleep call)
                datetime.datetime.fromtimestamp(1736087002),  # +0s
                datetime.datetime.fromtimestamp(1736087004),  # +2s (post-sleep call)
                datetime.datetime.fromtimestamp(1736087005),  # +1s
                datetime.datetime.fromtimestamp(1736087006),  # +1s (post-sleep call)
            ],
            [
                datetime.datetime.fromtimestamp(1736087000),  # start ts
                datetime.datetime.fromtimestamp(1736087002),  # +3s
                datetime.datetime.fromtimestamp(1736087004),  # +1s (post-sleep call)
                datetime.datetime.fromtimestamp(1736087006),  # +4s
            ],
            7,
            [1, 2, 1],
        ),
    ],
)
def test_throttle(
    client_throttle_sec: int,
    dt_now_call_timestamps: List[datetime.datetime],
    mocked_time_of_last_call: List[datetime.datetime],
    expected_datetime_now_call_cnt: int,
    expected_sleep_call_args: List[int],
) -> None:
    api_base_client = ThrottledAPIBaseClient(
        base_api_url="google.com",
        max_api_call_retries=3,
        seconds_between_api_calls=client_throttle_sec,
    )
    # NOTE: mocking datetime is funky. Had to follow this advice: https://stackoverflow.com/a/70598060
    with patch("lastfm_recs_scraper.utils.http_utils.datetime", wraps=datetime.datetime) as mock_dt:
        mock_dt.now.side_effect = dt_now_call_timestamps
        with patch("lastfm_recs_scraper.utils.http_utils.sleep") as mock_sleep:
            mock_sleep.return_value = None
            assert api_base_client._throttle_period == datetime.timedelta(seconds=client_throttle_sec)
            for i in range(len(mocked_time_of_last_call)):
                api_base_client._throttle()
                api_base_client._time_of_last_call = mocked_time_of_last_call[i]
            mock_sleep.assert_has_calls([call.sleep(expected_arg) for expected_arg in expected_sleep_call_args])
            mock_dt.assert_has_calls([call.now() for _ in range(expected_datetime_now_call_cnt)])


# TODO: make assertions that _throttle is called for all apiclient classes
@pytest.mark.parametrize(
    "subclass, expected_base_domain",
    [
        (RedAPIClient, "redacted.sh"),
        (LastFMAPIClient, "ws.audioscrobbler.com"),
        (MusicBrainzAPIClient, "musicbrainz.org"),
    ],
)
def test_init_throttled_api_client(
    subclass: ThrottledAPIBaseClient,
    expected_base_domain: str,
    api_client_to_app_config_keys: Dict[str, Dict[str, str]],
    valid_app_config: AppConfig,
) -> None:
    test_instance = subclass(app_config=valid_app_config)
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


# TODO: add unit tests for other endpoint actions if they start getting used (i.e. collage adding)
@pytest.mark.parametrize(
    "action, expected_top_keys, should_fail, exception_type, exception_message",
    [
        ("browse", set(["currentPage", "pages", "results"]), False, None, None),
        ("usersearch", set(), True, ValueError, "Unexpected/Non-permitted*"),
        ("somefakeaction", set(), True, ValueError, "Unexpected/Non-permitted*"),
        ("download", None, False, None, None),
    ],
)
def test_request_red_api(
    action: str,
    expected_top_keys: Optional[Set[str]],
    should_fail: bool,
    exception_type: Optional[Exception],
    exception_message: Optional[str],
    valid_app_config: AppConfig,
) -> None:
    with patch("requests.Session.get", side_effect=mock_red_session_get_side_effect) as mock_sesh_get:
        red_client = RedAPIClient(app_config=valid_app_config)
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
        ("album.search", set(), True, ValueError, "Unexpected method provided to lastfm api helper*"),
        ("fake.method", set(), True, ValueError, "Unexpected method provided to lastfm api helper*"),
    ],
)
def test_request_lastfm_api(
    method: str,
    expected_top_keys: Set[str],
    should_fail: bool,
    exception_type: Optional[Exception],
    exception_message: Optional[str],
    valid_app_config: AppConfig,
) -> None:
    with patch("requests.Session.get", side_effect=mock_last_fm_session_get_side_effect) as mock_sesh_get:
        lfm_client = LastFMAPIClient(app_config=valid_app_config)
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
            ), f"Expected result from request_lastfm_api to be of type dict, but was of type: {type(result)}"
            assert expected_top_keys == set(
                result.keys()
            ), f"Unexpected mismatch in top-level JSON keys for request_lastfm_api response."


@pytest.mark.parametrize(
    "entity_type, expected_mbid, should_fail, exception_type, exception_message",
    [
        ("release", "d211379d-3203-47ed-a0c5-e564815bb45a", False, None, None),
        (
            "release-group",
            "d211379d-3203-47ed-a0c5-e564815bb45a",
            True,
            ValueError,
            "Unexpected entity-type provided to musicbrainze api helper. Expected 'release'.",
        ),
        (
            "album",
            "some-fake-mbid-here",
            True,
            ValueError,
            "Unexpected entity-type provided to musicbrainze api helper. Expected 'release'.",
        ),
        (
            "song",
            "some-other-fake-mbid-here",
            True,
            ValueError,
            "Unexpected entity-type provided to musicbrainze api helper. Expected 'release'.",
        ),
    ],
)
def test_request_musicbrainz_api(
    entity_type: str,
    expected_mbid: str,
    should_fail: bool,
    exception_type: Optional[Exception],
    exception_message: Optional[str],
    valid_app_config: AppConfig,
) -> None:
    with patch("requests.Session.get", side_effect=mock_mb_session_get_side_effect) as mock_sesh_get:
        mb_client = MusicBrainzAPIClient(app_config=valid_app_config)
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
