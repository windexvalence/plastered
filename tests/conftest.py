import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
import yaml

from plastered.run_cache.run_cache import CacheType, RunCache
from plastered.utils.red_utils import (
    EncodingEnum,
    FormatEnum,
    MediaEnum,
    RedFormat,
    RedUserDetails,
)

TEST_DIR_ABS_PATH = os.path.dirname(os.path.abspath(__file__))
PROJECT_ABS_PATH = os.path.abspath(os.getenv("APP_DIR"))
ROOT_MODULE_ABS_PATH = os.path.join(PROJECT_ABS_PATH, "plastered")

from plastered.config.config_parser import AppConfig

MOCK_RESOURCES_DIR_PATH = os.path.join(TEST_DIR_ABS_PATH, "resources")
MOCK_JSON_RESPONSES_DIR_PATH = os.path.join(MOCK_RESOURCES_DIR_PATH, "mock_api_responses")
MOCK_HTML_RESPONSES_DIR_PATH = os.path.join(MOCK_RESOURCES_DIR_PATH, "mock_browser_html")
INVALID_CONFIGS_DIR_PATH = os.path.join(MOCK_RESOURCES_DIR_PATH, "invalid_configs")
EXAMPLES_DIR_PATH = os.path.join(PROJECT_ABS_PATH, "examples")
_RED_MOCK_BROWSE_JSON_FILEPATH = os.path.join(MOCK_JSON_RESPONSES_DIR_PATH, "red_browse_api_response.json")
_RED_MOCK_BROWSE_EMPTY_JSON_FILEPATH = os.path.join(
    MOCK_JSON_RESPONSES_DIR_PATH, "red_browse_api_no_results_response.json"
)
_RED_MOCK_GROUP_JSON_FILEPATH = os.path.join(MOCK_JSON_RESPONSES_DIR_PATH, "mock_red_group_response.json")
_RED_MOCK_USER_STATS_JSON_FILEPATH = os.path.join(MOCK_JSON_RESPONSES_DIR_PATH, "red_userstats_response.json")
_RED_MOCK_USER_TORRENTS_JSON_FILEPATH = os.path.join(MOCK_JSON_RESPONSES_DIR_PATH, "red_user_torrents_response.json")
_LFM_MOCK_ALBUM_INFO_JSON_FILEPATH = os.path.join(MOCK_JSON_RESPONSES_DIR_PATH, "lfm_album_info_api_response.json")
_LFM_MOCK_TRACK_INFO_JSON_FILEPATH = os.path.join(MOCK_JSON_RESPONSES_DIR_PATH, "lfm_track_info_api_response.json")
# TODO: create this mock resource file + secret
_LFM_MOCK_TRACK_INFO_NO_ALBUM_JSON_FILEPATH = os.path.join(
    MOCK_JSON_RESPONSES_DIR_PATH, "lfm_track_info_no_album_api_response.json"
)
_MUSICBRAINZ_MOCK_JSON_FILEPATH = os.path.join(MOCK_JSON_RESPONSES_DIR_PATH, "musicbrainz_release_api_response.json")
_MUSICBRAINZ_MOCK_TRACK_ARID_JSON_FILEPATH = os.path.join(
    MOCK_JSON_RESPONSES_DIR_PATH, "mb_track_search_tuss_arid.json"
)
_MUSICBRAINZ_MOCK_TRACK_ARTIST_NAME_JSON_FILEPATH = os.path.join(
    MOCK_JSON_RESPONSES_DIR_PATH, "mb_track_search_tuss_artist_name.json"
)


# boilerplate for marking tests which should only run on release builds with the `--releasetests` flag
# https://docs.pytest.org/en/latest/example/simple.html#control-skipping-of-tests-according-to-command-line-option
def pytest_addoption(parser):
    parser.addoption(
        "--releasetests", action="store_true", default=False, help="run release tests in addition to standard tests"
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "releasetest: mark test as a release-only test which should be skipped on non-release builds."
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--releasetests"):
        # --releasetests given in cli: do not skip release tests
        return
    skip_release = pytest.mark.skip(reason="need --releasetests option to run")
    for item in items:
        if "releasetest" in item.keywords:
            item.add_marker(skip_release)


def load_mock_response_json(json_filepath: str) -> Dict[str, Any]:
    """Utility function to load and return the mock API json blob located at the specified json_filepath."""
    with open(json_filepath, "r") as f:
        json_data = json.load(f)
    return json_data


_RED_ACTIONS_TO_MOCK_JSON = {
    "browse": load_mock_response_json(json_filepath=_RED_MOCK_BROWSE_JSON_FILEPATH),
    "torrentgroup": load_mock_response_json(json_filepath=_RED_MOCK_GROUP_JSON_FILEPATH),
    "community_stats": load_mock_response_json(json_filepath=_RED_MOCK_USER_STATS_JSON_FILEPATH),
    "user_torrents": load_mock_response_json(json_filepath=_RED_MOCK_USER_TORRENTS_JSON_FILEPATH),
}


@pytest.fixture(scope="session")
def valid_config_filepath() -> str:
    return os.path.join(EXAMPLES_DIR_PATH, "config.yaml")


@pytest.fixture(scope="session")
def minimal_valid_config_filepath() -> str:
    return os.path.join(EXAMPLES_DIR_PATH, "minimal_config.yaml")


@pytest.fixture(scope="session")
def valid_config_raw_data(valid_config_filepath: str) -> Dict[str, Any]:
    with open(valid_config_filepath, "r") as f:
        raw_config_data = yaml.safe_load(f.read())
    return raw_config_data


@pytest.fixture(scope="session")
def minimal_valid_config_raw_data(minimal_valid_config_filepath: str) -> Dict[str, Any]:
    with open(minimal_valid_config_filepath, "r") as f:
        raw_config_data = yaml.safe_load(f.read())
    return raw_config_data


@pytest.fixture(scope="session")
def minimal_valid_app_config(minimal_valid_config_filepath: str) -> AppConfig:
    return AppConfig(config_filepath=minimal_valid_config_filepath, cli_params=dict())


@pytest.fixture(scope="session")
def mock_action_to_red_json_responses() -> Dict[str, Dict[str, Any]]:
    return {
        "browse": load_mock_response_json(json_filepath=_RED_MOCK_BROWSE_JSON_FILEPATH),
    }


@pytest.fixture(scope="session")
def mock_red_browse_non_empty_response() -> Dict[str, Any]:
    return load_mock_response_json(json_filepath=_RED_MOCK_BROWSE_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_red_browse_empty_response() -> Dict[str, Any]:
    return load_mock_response_json(json_filepath=_RED_MOCK_BROWSE_EMPTY_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_red_group_response() -> Dict[str, Any]:
    return load_mock_response_json(json_filepath=_RED_MOCK_GROUP_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_red_user_stats_response() -> Dict[str, Any]:
    return load_mock_response_json(json_filepath=_RED_MOCK_USER_STATS_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_red_user_torrents_response() -> Dict[str, Any]:
    return load_mock_response_json(json_filepath=_RED_MOCK_USER_TORRENTS_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_red_user_details(mock_red_user_torrents_response: Dict[str, Any]) -> RedUserDetails:
    return RedUserDetails(
        user_id=69, snatched_count=5216, snatched_torrents_list=mock_red_user_torrents_response["response"]["snatched"]
    )


@pytest.fixture(scope="session")
def mock_lfm_album_info_json() -> Dict[str, Any]:
    return load_mock_response_json(json_filepath=_LFM_MOCK_ALBUM_INFO_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_full_lfm_track_info_json() -> Dict[str, Any]:
    return load_mock_response_json(json_filepath=_LFM_MOCK_TRACK_INFO_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_no_album_lfm_track_info_json() -> Dict[str, Any]:
    return load_mock_response_json(json_filepath=_LFM_MOCK_TRACK_INFO_NO_ALBUM_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_musicbrainz_release_json() -> Dict[str, Any]:
    return load_mock_response_json(json_filepath=_MUSICBRAINZ_MOCK_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_musicbrainz_track_search_arid_json() -> Dict[str, Any]:
    return load_mock_response_json(json_filepath=_MUSICBRAINZ_MOCK_TRACK_ARID_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_musicbrainz_track_search_artist_name_json() -> Dict[str, Any]:
    return load_mock_response_json(json_filepath=_MUSICBRAINZ_MOCK_TRACK_ARTIST_NAME_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_musicbrainz_track_search_no_release_name_json() -> Dict[str, Any]:
    raw_data = load_mock_response_json(json_filepath=_MUSICBRAINZ_MOCK_TRACK_ARTIST_NAME_JSON_FILEPATH)
    del raw_data["recordings"][0]["releases"][0]["title"]
    return raw_data


@pytest.fixture(scope="session")
def cache_root_dir_path(tmp_path_factory: pytest.FixtureRequest) -> Path:
    """
    Fixture which creates a session-scoped temporary root cache directory and returns the pathlib.Path object for it.
    """
    return tmp_path_factory.mktemp("cache")


@pytest.fixture(scope="session")
def api_cache_dir_path(cache_root_dir_path: Path) -> Path:
    """
    Fixture which creates a session-scoped API cache directory and returns the pathlib.Path object for it.
    """
    api_cache_path = cache_root_dir_path / "api"
    api_cache_path.mkdir()
    return api_cache_path


@pytest.fixture(scope="session")
def scraper_cache_dir_path(cache_root_dir_path: Path) -> Path:
    """
    Fixture which creates a session-scoped Scraper cache directory and returns the pathlib.Path object for it.
    """
    scraper_cache_path = cache_root_dir_path / "scraper"
    scraper_cache_path.mkdir()
    return scraper_cache_path


@pytest.fixture(scope="function")
def valid_app_config(valid_config_filepath: str, cache_root_dir_path: Path) -> AppConfig:
    """
    Function-scoped valid AppConfig fixture, with cache root dir
    overridden to use the session-scoped tmp cache root dir fixture
    """
    app_config = AppConfig(config_filepath=valid_config_filepath, cli_params=dict())
    app_config._base_cache_directory_path = str(cache_root_dir_path)
    return app_config


@pytest.fixture(scope="session")
def api_run_cache(valid_config_filepath: str) -> RunCache:
    app_config = AppConfig(config_filepath=valid_config_filepath, cli_params=dict())
    return RunCache(app_config=app_config, cache_type=CacheType.API)


@pytest.fixture(scope="session")
def scraper_run_cache(valid_config_filepath: AppConfig) -> RunCache:
    app_config = AppConfig(config_filepath=valid_config_filepath, cli_params=dict())
    return RunCache(app_config=app_config, cache_type=CacheType.SCRAPER)


def mock_red_session_get_side_effect(*args, **kwargs) -> Dict[str, Any]:
    """
    Helper test function to pass as the value for any
    patch('requests.Session.get', ...) mocks on a RedAPIClient test case.
    This ensures that the subsequent response's json()/content value is properly overridden with the desired data.
    """
    url_val = kwargs["url"]
    m = re.match(r"^.*\?action=([^&]+)&.*", url_val)
    red_action = m.groups()[0]
    resp_mock = MagicMock(name="json")
    mock_json = _RED_ACTIONS_TO_MOCK_JSON[red_action]
    resp_mock.json.return_value = mock_json
    resp_mock.status_code.return_value = 200
    return resp_mock


def mock_red_snatch_get_side_effect() -> bytes:
    resp_mock = MagicMock()
    resp_mock.content.return_value = bytes("fakebytes", encoding="utf-8")
    resp_mock.status_code.return_value = 200
    return resp_mock


def mock_lfm_session_get_side_effect(*args, **kwargs) -> Dict[str, Any]:
    """
    Helper test function to pass as the value for any
    patch('requests.Session.get', ...) mocks on a LFMAPIClient test case.
    This ensures that the subsequent response's json() value is properly overridden with the desired data.
    """
    url_val = kwargs["url"]
    resp_mock = MagicMock(name="json")
    mock_json = None
    if "album.getinfo" in url_val:
        mock_json = load_mock_response_json(json_filepath=_LFM_MOCK_ALBUM_INFO_JSON_FILEPATH)
    elif "track.getinfo" in url_val:
        mock_json = load_mock_response_json(json_filepath=_LFM_MOCK_TRACK_INFO_JSON_FILEPATH)
    resp_mock.json.return_value = mock_json
    return resp_mock


def mock_mb_session_get_side_effect(*args, **kwargs) -> Dict[str, Any]:
    """
    Helper test function to pass as the value for any
    patch('requests.Session.get', ...) mocks on a MusicBrainzAPIClient test case.
    This ensures that the subsequent response's json() value is properly overridden with the desired data.
    """
    resp_mock = MagicMock(name="json")
    mock_json = load_mock_response_json(json_filepath=_MUSICBRAINZ_MOCK_JSON_FILEPATH)
    resp_mock.json.return_value = mock_json
    return resp_mock


@pytest.fixture(scope="session")
def expected_red_format_list() -> List[RedFormat]:
    return [
        RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.SACD),
        RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
        RedFormat(
            format=FormatEnum.FLAC,
            encoding=EncodingEnum.LOSSLESS,
            media=MediaEnum.CD,
            cd_only_extras="haslog=100&hascue=1",
        ),
        RedFormat(
            format=FormatEnum.FLAC,
            encoding=EncodingEnum.LOSSLESS,
            media=MediaEnum.CD,
            cd_only_extras="haslog=100&hascue=0",
        ),
        RedFormat(
            format=FormatEnum.FLAC,
            encoding=EncodingEnum.LOSSLESS,
            media=MediaEnum.CD,
            cd_only_extras="haslog=0&hascue=0",
        ),
        RedFormat(format=FormatEnum.MP3, encoding=EncodingEnum.MP3_V0, media=MediaEnum.ANY),
    ]
