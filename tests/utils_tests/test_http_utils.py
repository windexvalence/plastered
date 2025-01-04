from datetime import timedelta
from typing import Dict, Optional, Set
from unittest.mock import patch

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
    expected_throttle_period = timedelta(seconds=valid_app_config.get_cli_option(app_config_keys["period"]))
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
        if should_fail:
            with pytest.raises(exception_type, match=exception_message):
                result = red_client.request_api(action=action, params="fakekey=fakevalue")
                mock_sesh_get.assert_not_called()
            return
        result = red_client.request_api(action=action, params="fakekey=fakevalue&someotherkey=someothervalue")
        if action == "download":
            assert result is not None
        else:
            mock_sesh_get.assert_called_once_with(url=f"https://redacted.sh/ajax.php?action={action}&fakekey=fakevalue&someotherkey=someothervalue")
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
        if should_fail:
            with pytest.raises(exception_type, match=exception_message):
                result = lfm_client.request_api(method=method, params="fakekey=fakevalue")
        else:
            result = lfm_client.request_api(method=method, params="fakekey=val&other=bla")
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
        if should_fail:
            with pytest.raises(exception_type, match=exception_message):
                result = mb_client.request_api(entity_type=entity_type, mbid=expected_mbid)
        else:
            result = mb_client.request_api(entity_type="release", mbid=expected_mbid)
            assert isinstance(result, dict), f"Expected result from request_api to be a dict, but was: {type(result)}"
            assert "id" in result.keys(), f"Missing expected top-level key in musicbrainz response: 'id'"
            response_mbid = result["id"]
            assert (
                response_mbid == expected_mbid
            ), f"Mismatch between actual response mbid ('{response_mbid}') and expected mbid ('{expected_mbid}')"
