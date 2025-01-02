import os
from itertools import product
from typing import Any, Dict, List, Optional
from unittest.mock import PropertyMock, patch

import pytest

from lastfm_recs_scraper.config.config_parser import (
    AppConfig,
    _get_cd_only_extras_string,
    _load_red_formats_from_config,
)
from lastfm_recs_scraper.config.config_schema import (
    CLI_SNATCH_DIRECTORY_KEY,
    FORMAT_PREFERENCES_KEY,
)
from lastfm_recs_scraper.utils.exceptions import AppConfigException
from lastfm_recs_scraper.utils.red_utils import RedFormat
from tests.conftest import (
    INVALID_CONFIGS_DIR_PATH,
    MOCK_RESOURCES_DIR_PATH,
    expected_red_format_list,
    valid_app_config,
    valid_config_raw_data,
)

_EXPECTED_FORMAT_PREFERENCE_LENGTH = 6


# [{'log': -1, 'has_cue': False},
#  {'log': -1, 'has_cue': True},
#  {'log': 0, 'has_cue': False},
#  {'log': 0, 'has_cue': True},
#  {'log': 1, 'has_cue': False},
#  {'log': 1, 'has_cue': True},
#  {'log': 100, 'has_cue': False},
#  {'log': 100, 'has_cue': True}]
@pytest.mark.parametrize(
    "conf_dict, expected_result",
    [
        ({"log": -1, "has_cue": False}, "haslog=-1&hascue=0"),
        ({"log": -1, "has_cue": True}, "haslog=-1&hascue=1"),
        ({"log": 0, "has_cue": False}, "haslog=0&hascue=0"),
        ({"log": 0, "has_cue": True}, "haslog=0&hascue=1"),
        ({"log": 1, "has_cue": False}, "haslog=1&hascue=0"),
        ({"log": 1, "has_cue": True}, "haslog=1&hascue=1"),
        ({"log": 100, "has_cue": False}, "haslog=100&hascue=0"),
        ({"log": 100, "has_cue": True}, "haslog=100&hascue=1"),
    ],
)
def test_get_cd_only_extras_string(
    expected_red_format_list: List[RedFormat], conf_dict: Dict[str, str], expected_result: str
) -> None:
    actual = _get_cd_only_extras_string(cd_only_extras_conf_data=conf_dict)
    assert actual == expected_result, f"Expected '{expected_result}' but got '{actual}'"


def test_load_red_formats_from_config(
    expected_red_format_list: List[RedFormat], valid_config_raw_data: Dict[str, Any]
) -> None:
    result = _load_red_formats_from_config(format_prefs_config_data=valid_config_raw_data[FORMAT_PREFERENCES_KEY])
    print(f"type(result[0]): {type(result[0])}")
    print(f"result[0].__class__.__name__: {result[0].__class__.__name__}")
    assert isinstance(result, list), f"Expected result type to be list, but got '{type(result)}'"
    assert (
        len(result) == _EXPECTED_FORMAT_PREFERENCE_LENGTH
    ), f"Expected RedFormat list to contain {_EXPECTED_FORMAT_PREFERENCE_LENGTH} elements, but found {len(result)}"
    assert all([isinstance(elem, RedFormat) for elem in result]), f"Expected all elements to be of class 'RedFormat'"
    for i, actual_format in enumerate(result):
        expected_format = expected_red_format_list[i]
        assert (
            actual_format == expected_format
        ), f"Unexpected RedFormat mismatch on {i}'th element of RedFormats list: expected: {expected_format}, actual: {actual_format}"


@pytest.mark.parametrize(
    "mock_format_prefs_config_data, exception, exception_msg",
    [
        (
            [
                {"preference": {"format": "FLAC", "encoding": "24bit+Lossless", "media": "SACD"}},
                {"preference": {"format": "FLAC", "encoding": "24bit+Lossless", "media": "SACD"}},
            ],
            AppConfigException,
            "Invalid 'format_preferences' configuration: duplicate entries",
        ),
        (
            [
                {"preference": {"format": "FLAC", "encoding": "24bit+Lossless", "media": "SACD"}},
                {
                    "preference": {
                        "format": "FLAC",
                        "encoding": "Lossless",
                        "media": "CD",
                        "cd_only_extras": {"log": 100, "has_cue": True},
                    }
                },
                {
                    "preference": {
                        "format": "FLAC",
                        "encoding": "Lossless",
                        "media": "CD",
                        "cd_only_extras": {"log": 100, "has_cue": True},
                    }
                },
            ],
            AppConfigException,
            "Invalid 'format_preferences' configuration: duplicate entries",
        ),
    ],
)
def test_invalid_dupe_load_red_formats_from_config(
    mock_format_prefs_config_data: List[Dict[str, Any]],
    exception: Exception,
    exception_msg: str,
) -> None:
    with pytest.raises(exception, match=exception_msg):
        _load_red_formats_from_config(format_prefs_config_data=mock_format_prefs_config_data)


@pytest.mark.parametrize(
    "cli_params, expected_opts_vals",
    [
        (
            dict(),
            {
                "red_api_key": "1234notarealapikey",
                "last_fm_api_key": "5678alsonotarealapikey",
                "last_fm_username": "fake-username",
                "last_fm_password": "fake-password",
            },
        ),
        (
            {"red_api_key": "cli-override-red-api-key"},
            {
                "red_api_key": "cli-override-red-api-key",
                "last_fm_api_key": "5678alsonotarealapikey",
                "last_fm_username": "fake-username",
                "last_fm_password": "fake-password",
            },
        ),
        (
            {"last_fm_api_key": "cli-override-last-fm-api-key"},
            {
                "red_api_key": "1234notarealapikey",
                "last_fm_api_key": "cli-override-last-fm-api-key",
                "last_fm_username": "fake-username",
                "last_fm_password": "fake-password",
            },
        ),
        (
            {"last_fm_username": "cli-override-last-fm-username"},
            {
                "red_api_key": "1234notarealapikey",
                "last_fm_api_key": "5678alsonotarealapikey",
                "last_fm_username": "cli-override-last-fm-username",
                "last_fm_password": "fake-password",
            },
        ),
        (
            {"last_fm_password": "cli-override-last-fm-password"},
            {
                "red_api_key": "1234notarealapikey",
                "last_fm_api_key": "5678alsonotarealapikey",
                "last_fm_username": "fake-username",
                "last_fm_password": "cli-override-last-fm-password",
            },
        ),
    ],
)
def test_app_config_constructor(
    valid_config_filepath: str, cli_params: Dict[str, Any], expected_opts_vals: Dict[str, Any]
) -> None:
    app_config = AppConfig(config_filepath=valid_config_filepath, cli_params=cli_params)
    for opt_key, expected_value in expected_opts_vals.items():
        actual_value = app_config.get_cli_option(opt_key)
        assert (
            actual_value == expected_value
        ), f"Unexpected '{opt_key}' value: '{actual_value}'. Expected '{expected_value}'"


@pytest.mark.parametrize(
    "config_filepath, cli_params, exception_type, exception_msg",
    [
        (
            "/some_fake/path/nonexistent/filepath.yaml",
            {},
            AppConfigException,
            "Provided config filepath does not exist",
        ),
        (
            os.path.join(INVALID_CONFIGS_DIR_PATH, "invalid_config.yaml"),
            {},
            AppConfigException,
            "Provided yaml configuration's schema is invalid",
        ),
    ],
)
def test_invalid_app_config_constructor(
    config_filepath: str, cli_params: Dict[str, Any], exception_type: Exception, exception_msg: str
) -> None:
    with pytest.raises(exception_type, match=exception_msg):
        app_config = AppConfig(config_filepath=config_filepath, cli_params=cli_params)


@pytest.mark.parametrize(
    "final_cli_options_overrides, should_fail, exception, exception_msg",
    [
        ({CLI_SNATCH_DIRECTORY_KEY: "/some/fake/path"}, True, AppConfigException, "must exist and must be a directory"),
        (
            {CLI_SNATCH_DIRECTORY_KEY: "/requirements.txt"},
            True,
            AppConfigException,
            "must exist and must be a directory",
        ),
        ({CLI_SNATCH_DIRECTORY_KEY: MOCK_RESOURCES_DIR_PATH}, False, None, None),
    ],
)
def test_validate_final_cli_options(
    valid_app_config: AppConfig,
    final_cli_options_overrides: Dict[str, Any],
    should_fail: bool,
    exception: Optional[Exception],
    exception_msg: Optional[str],
) -> None:
    mock_final_cli_options = {**valid_app_config.get_all_options(), **final_cli_options_overrides}
    valid_app_config._cli_options = mock_final_cli_options
    if should_fail:
        with pytest.raises(exception, match=exception_msg):
            valid_app_config._validate_final_cli_options()
    else:
        valid_app_config._validate_final_cli_options()


def test_pretty_print_config(valid_config_filepath: str) -> None:
    with patch("yaml.dump") as mock_yaml_dump:
        app_config = AppConfig(config_filepath=valid_config_filepath, cli_params=dict())
        app_config.pretty_print_config()
        mock_yaml_dump.assert_called_once()


def test_pretty_print_preference_ordering(valid_config_filepath: str) -> None:
    with patch("yaml.dump") as mock_yaml_dump:
        app_config = AppConfig(config_filepath=valid_config_filepath, cli_params=dict())
        app_config.pretty_print_preference_ordering()
        mock_yaml_dump.assert_called_once()


# TODO: add unit tests to ensure the jsonschema validation raises exceptions when expected
