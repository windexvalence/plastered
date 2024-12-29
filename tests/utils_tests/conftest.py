import json
import os
from typing import Any, Dict

import pytest
import requests

from lastfm_recs_scraper.utils.constants import (
    LAST_FM_API_BASE_URL,
    MUSICBRAINZ_API_BASE_URL,
    RED_API_BASE_URL,
)
from lastfm_recs_scraper.utils.http_utils import initialize_api_client
from tests.conftest import (
    MOCK_JSON_RESPONSES_DIR_PATH,
    TEST_DIR_ABS_PATH,
    load_mock_response_json,
)

_LAST_FM_MOCK_ALBUM_INFO_JSON_FILEPATH = os.path.join(
    MOCK_JSON_RESPONSES_DIR_PATH, "last_fm_album_info_api_response.json"
)
_LAST_FM_MOCK_TRACK_INFO_JSON_FILEPATH = os.path.join(
    MOCK_JSON_RESPONSES_DIR_PATH, "last_fm_track_info_api_response.json"
)
_MUSICBRAINZ_MOCK_JSON_FILEPATH = os.path.join(MOCK_JSON_RESPONSES_DIR_PATH, "musicbrainz_release_api_response.json")

EXPECTED_RETRIES = 2
EXPECTED_SECONDS = 5


@pytest.fixture(scope="session")
def mock_method_to_last_fm_json_responses() -> Dict[str, Dict[str, Any]]:
    return {
        "album.getinfo": load_mock_response_json(json_filepath=_LAST_FM_MOCK_ALBUM_INFO_JSON_FILEPATH),
        "track.getinfo": load_mock_response_json(json_filepath=_LAST_FM_MOCK_TRACK_INFO_JSON_FILEPATH),
    }


@pytest.fixture(scope="session")
def mock_last_fm_album_info_json() -> Dict[str, Any]:
    return load_mock_response_json(json_filepath=_LAST_FM_MOCK_ALBUM_INFO_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_last_fm_track_info_json() -> Dict[str, Any]:
    return load_mock_response_json(json_filepath=_LAST_FM_MOCK_TRACK_INFO_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_musicbrainz_release_json() -> Dict[str, Any]:
    return load_mock_response_json(json_filepath=_MUSICBRAINZ_MOCK_JSON_FILEPATH)


@pytest.fixture(scope="session")
def api_clients_dict() -> Dict[str, requests.Session]:
    return {
        "redacted": initialize_api_client(
            base_api_url=RED_API_BASE_URL,
            max_api_call_retries=EXPECTED_RETRIES,
            seconds_between_api_calls=EXPECTED_SECONDS,
        ),
        "last_fm": initialize_api_client(
            base_api_url=LAST_FM_API_BASE_URL,
            max_api_call_retries=EXPECTED_RETRIES,
            seconds_between_api_calls=EXPECTED_SECONDS,
        ),
        "musicbrainz": initialize_api_client(
            base_api_url=MUSICBRAINZ_API_BASE_URL,
            max_api_call_retries=EXPECTED_RETRIES,
            seconds_between_api_calls=EXPECTED_SECONDS,
        ),
    }
