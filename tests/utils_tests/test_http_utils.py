from typing import Any, Dict, Optional, Set
from unittest.mock import Mock

import pytest
import requests

from lastfm_recs_scraper.utils.constants import (
    LAST_FM_API_BASE_URL,
    MUSICBRAINZ_API_BASE_URL,
    RED_API_BASE_URL,
)
from lastfm_recs_scraper.utils.http_utils import (
    initialize_api_client,
    request_lastfm_api,
    request_musicbrainz_api,
    request_red_api,
)
from tests.utils_tests.conftest import (
    mock_method_to_last_fm_json_responses,
    mock_musicbrainz_release_json,
    mock_action_to_red_json_responses,
)

_EXPECTED_RETRIES = 2
_EXPECTED_SECONDS = 5


@pytest.fixture(scope="session")
def api_clients_dict() -> Dict[str, requests.Session]:
    return {
        "redacted": initialize_api_client(
            base_api_url=RED_API_BASE_URL,
            max_api_call_retries=_EXPECTED_RETRIES,
            seconds_between_api_calls=_EXPECTED_SECONDS,
        ),
        "last_fm": initialize_api_client(
            base_api_url=LAST_FM_API_BASE_URL,
            max_api_call_retries=_EXPECTED_RETRIES,
            seconds_between_api_calls=_EXPECTED_SECONDS,
        ),
        "musicbrainz": initialize_api_client(
            base_api_url=MUSICBRAINZ_API_BASE_URL,
            max_api_call_retries=_EXPECTED_RETRIES,
            seconds_between_api_calls=_EXPECTED_SECONDS,
        ),
    }


@pytest.mark.parametrize(
    "api_client_name, expected_adapter_domain",
    [
        ("redacted", "redacted.sh"),
        ("last_fm", "ws.audioscrobbler.com"),
        ("musicbrainz", "musicbrainz.org"),
    ],
)
def test_initialize_api_client(
    api_clients_dict: Dict[str, requests.Session],
    api_client_name: str,
    expected_adapter_domain: str,
) -> None:
    api_client = api_clients_dict[api_client_name]
    adapter = api_client.get_adapter(expected_adapter_domain)
    actual_retries = adapter.max_retries.total
    assert (
        actual_retries == _EXPECTED_RETRIES
    ), f"Expected session's retry value to be {_EXPECTED_RETRIES}, but got {actual_retries} instead."



# TODO: add unit tests for other endpoint actions if they start getting used (i.e. collage adding)
@pytest.mark.parametrize(
    "action, expected_top_keys, should_fail, exception_type, exception_message",
    [
        ("browse", set(["currentPage", "pages", "results"]), False, None, None),
        ("usersearch", set(), True, ValueError, "Unexpected/Non-permitted*"),
        ("somefakeaction", set(), True, ValueError, "Unexpected/Non-permitted*"),
    ]
)
def test_request_red_api(
    api_clients_dict: Dict[str, requests.Session],
    mock_action_to_red_json_responses: Dict[str, Dict[str, Any]],
    action: str,
    expected_top_keys: Set[str],
    should_fail: bool,
    exception_type: Optional[Exception],
    exception_message: Optional[str],
) -> None:
    api_client = api_clients_dict["redacted"]
    if should_fail:
        with pytest.raises(exception_type, match=exception_message):
            result = request_red_api(red_client=api_client, action=action, params="fakekey=fakevalue")
    else:
        api_client.get = Mock(name="get")
        api_client.get.return_value = mock_action_to_red_json_responses[action]
        result = request_red_api(
            red_client=api_client,
            action=action,
            params="fakekey=fakevalue&someotherkey=someothervalue",
        )
        assert isinstance(result, dict), f"Expected result from request_red_api to be of type dict, but was of type: {type(result)}"
        assert expected_top_keys == set(result.keys()), f"Unexpected mismatch in top-level JSON keys for request_red_api response."


@pytest.mark.parametrize(
    "method, expected_top_keys, should_fail, exception_type, exception_message",
    [
        ("album.getinfo", set(["artist", "image", "listeners", "mbid", "name", "playcount", "tags", "tracks", "url", "wiki"]), False, None, None),
        ("track.getinfo", set(["album", "artist", "duration", "listeners", "mbid", "name", "playcount", "streamable", "toptags", "url"]), False, None, None),
        ("album.search", set(), True, ValueError, "Unexpected method provided to lastfm api helper*"),
        ("fake.method", set(), True, ValueError, "Unexpected method provided to lastfm api helper*"),
    ]
)
def test_request_lastfm_api(
    api_clients_dict: Dict[str, requests.Session],
    mock_method_to_last_fm_json_responses: Dict[str, Dict[str, Any]],
    method: str,
    expected_top_keys: Set[str],
    should_fail: bool,
    exception_type: Optional[Exception],
    exception_message: Optional[str],
) -> None:
    api_client = api_clients_dict["last_fm"]
    if should_fail:
        with pytest.raises(exception_type, match=exception_message):
            result = request_lastfm_api(last_fm_client=api_client, api_key="fake-api-key", method=method, params="fakekey=fakevalue")
    else:
        api_client.get = Mock(name="get")
        api_client.get.return_value = mock_method_to_last_fm_json_responses[method]
        result = request_lastfm_api(
            last_fm_client=api_client,
            api_key="fake-api-key",
            method=method,
            params="fakekey=fakevalue&someotherkey=someothervalue",
        )
        assert isinstance(result, dict), f"Expected result from request_lastfm_api to be of type dict, but was of type: {type(result)}"
        assert expected_top_keys == set(result.keys()), f"Unexpected mismatch in top-level JSON keys for request_lastfm_api response."


@pytest.mark.parametrize(
    "entity_type, expected_mbid, should_fail, exception_type, exception_message",
    [
        ("release", "d211379d-3203-47ed-a0c5-e564815bb45a", False, None, None),
        ("release-group", "d211379d-3203-47ed-a0c5-e564815bb45a", False, None, None),
        (
            "album",
            "some-fake-mbid-here",
            True,
            ValueError,
            "Unexpected entity-type provided to musicbrainze api helper. Expected either 'release-group' or 'release'.",
        ),
        (
            "song",
            "some-other-fake-mbid-here",
            True,
            ValueError,
            "Unexpected entity-type provided to musicbrainze api helper. Expected either 'release-group' or 'release'.",
        ),
    ],
)
def test_request_musicbrainz_api(
    api_clients_dict: Dict[str, requests.Session],
    mock_musicbrainz_release_json: Dict[str, Any],
    entity_type: str,
    expected_mbid: str,
    should_fail: bool,
    exception_type: Optional[Exception],
    exception_message: Optional[str],
) -> None:
    api_client = api_clients_dict["musicbrainz"]
    api_client.get = Mock(name="get")
    api_client.get.return_value = mock_musicbrainz_release_json
    if should_fail:
        with pytest.raises(exception_type, match=exception_message):
            result = request_musicbrainz_api(
                musicbrainz_client=api_client,
                entity_type=entity_type,
                mbid=expected_mbid,
            )
    else:
        result = request_musicbrainz_api(
            musicbrainz_client=api_client, entity_type="release", mbid=expected_mbid
        )
        assert isinstance(
            result, dict
        ), f"Expected result from request_musicbrainz_api to be of type dict, but was of type: {type(result)}"
        assert (
            "id" in result.keys()
        ), f"Missing expected top-level key in musicbrainz response: 'id'"
        response_mbid = result["id"]
        assert (
            response_mbid == expected_mbid
        ), f"Mismatch between actual response mbid ('{response_mbid}') and expected mbid ('{expected_mbid}')"
