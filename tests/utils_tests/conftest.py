import json
import os
from typing import Any, Dict

import pytest

from tests.conftest import TEST_DIR_ABS_PATH

_MOCK_JSON_RESPONSES_DIR_PATH = os.path.join(
    TEST_DIR_ABS_PATH, "utils_tests", "mock_api_responses"
)

# TODO: create the remaining mock JSON files here
_RED_MOCK_BROWSE_JSON_FILEPATH = os.path.join(
    _MOCK_JSON_RESPONSES_DIR_PATH, "red_browse_api_response.json"
)
_LAST_FM_MOCK_ALBUM_INFO_JSON_FILEPATH = os.path.join(
    _MOCK_JSON_RESPONSES_DIR_PATH, "last_fm_album_info_api_response.json"
)
_LAST_FM_MOCK_TRACK_INFO_JSON_FILEPATH = os.path.join(
    _MOCK_JSON_RESPONSES_DIR_PATH, "last_fm_track_info_api_response.json"
)
_MUSICBRAINZ_MOCK_JSON_FILEPATH = os.path.join(
    _MOCK_JSON_RESPONSES_DIR_PATH, "musicbrainz_release_api_response.json"
)


def _load_mock_response_json(json_filepath: str) -> Dict[str, Any]:
    """Utility function to load and return the mock API json blob located at the specified json_filepath."""
    with open(json_filepath, "r") as f:
        json_data = json.load(f)
    return json_data


@pytest.fixture(scope="session")
def mock_action_to_red_json_responses() -> Dict[str, Dict[str, Any]]:
    return {
        "browse": _load_mock_response_json(json_filepath=_RED_MOCK_BROWSE_JSON_FILEPATH),
    }


@pytest.fixture(scope="session")
def mock_method_to_last_fm_json_responses() -> Dict[str, Dict[str, Any]]:
    return {
        "album.getinfo": _load_mock_response_json(
            json_filepath=_LAST_FM_MOCK_ALBUM_INFO_JSON_FILEPATH
        ),
        "track.getinfo": _load_mock_response_json(
            json_filepath=_LAST_FM_MOCK_TRACK_INFO_JSON_FILEPATH
        ),
    }


@pytest.fixture(scope="session")
def mock_last_fm_track_info_json() -> Dict[str, Any]:
    return _load_mock_response_json(
        json_filepath=_LAST_FM_MOCK_TRACK_INFO_JSON_FILEPATH
    )


@pytest.fixture(scope="session")
def mock_musicbrainz_release_json() -> Dict[str, Any]:
    return _load_mock_response_json(json_filepath=_MUSICBRAINZ_MOCK_JSON_FILEPATH)
