import json
import os
import sys
from typing import Any, Dict, List

import pytest
import yaml

from lastfm_recs_scraper.utils.red_utils import (
    EncodingEnum,
    FormatEnum,
    MediaEnum,
    RedFormat,
)

TEST_DIR_ABS_PATH = os.path.dirname(os.path.abspath(__file__))
PROJECT_ABS_PATH = os.path.abspath(os.getenv("APP_DIR"))

from lastfm_recs_scraper.config.config_parser import AppConfig

MOCK_RESOURCES_DIR_PATH = os.path.join(TEST_DIR_ABS_PATH, "resources")
MOCK_JSON_RESPONSES_DIR_PATH = os.path.join(MOCK_RESOURCES_DIR_PATH, "mock_api_responses")
MOCK_HTML_RESPONSES_DIR_PATH = os.path.join(MOCK_RESOURCES_DIR_PATH, "mock_browser_html")
EXAMPLES_DIR_PATH = os.path.join(PROJECT_ABS_PATH, "examples")
_RED_MOCK_BROWSE_JSON_FILEPATH = os.path.join(MOCK_JSON_RESPONSES_DIR_PATH, "red_browse_api_response.json")
_RED_MOCK_BROWSE_EMPTY_JSON_FILEPATH = os.path.join(
    MOCK_JSON_RESPONSES_DIR_PATH, "red_browse_api_no_results_response.json"
)


def load_mock_response_json(json_filepath: str) -> Dict[str, Any]:
    """Utility function to load and return the mock API json blob located at the specified json_filepath."""
    with open(json_filepath, "r") as f:
        json_data = json.load(f)
    return json_data


# TODO: add unit tests and ensure project imports work here
@pytest.fixture(scope="session")
def valid_config_filepath() -> str:
    return os.path.join(EXAMPLES_DIR_PATH, "config.yaml")


@pytest.fixture(scope="session")
def valid_config_raw_data(valid_config_filepath: str) -> Dict[str, Any]:
    with open(valid_config_filepath, "r") as f:
        raw_config_data = yaml.safe_load(f.read())
    return raw_config_data


@pytest.fixture(scope="session")
def valid_app_config(valid_config_filepath: str) -> AppConfig:
    return AppConfig(config_filepath=valid_config_filepath, cli_params=dict())


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
