import os
from typing import Any
from unittest.mock import mock_open, patch

import pytest

from plastered.config.config_parser import (
    _SUMMARIES_DIRNAME,
    AppConfig,
    _get_cd_only_extras_string,
    _load_red_formats_from_config,
    load_init_config_template,
)
from plastered.config.config_schema import CLI_SNATCH_DIRECTORY_KEY, FORMAT_PREFERENCES_KEY
from plastered.utils.exceptions import AppConfigException
from plastered.utils.red_utils import RedFormat
from tests.conftest import INVALID_CONFIGS_DIR_PATH, MOCK_RESOURCES_DIR_PATH, ROOT_MODULE_ABS_PATH

_EXPECTED_FORMAT_PREFERENCE_LENGTH = 6


def test_load_init_config_template() -> None:
    expected_filepath_arg = os.path.join(ROOT_MODULE_ABS_PATH, "config", "init_conf.yaml")
    expected_result = "# top comment\nline1: # inline-comment\n\tline2\n"
    with patch(
        "builtins.open", new_callable=mock_open, read_data="# top comment\nline1: # inline-comment\n\tline2\n"
    ) as mock_open_builtin:
        actual_result = load_init_config_template()
        mock_open_builtin.assert_called_once_with(expected_filepath_arg)
        assert actual_result == expected_result, f"Expected result: '{expected_result}', but got '{actual_result}'"


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
    expected_red_format_list: list[RedFormat], conf_dict: dict[str, str], expected_result: str
) -> None:
    actual = _get_cd_only_extras_string(cd_only_extras_conf_data=conf_dict)
    assert actual == expected_result, f"Expected '{expected_result}' but got '{actual}'"


def test_load_red_formats_from_config(
    expected_red_format_list: list[RedFormat], valid_config_raw_data: dict[str, Any]
) -> None:
    result = _load_red_formats_from_config(format_prefs_config_data=valid_config_raw_data[FORMAT_PREFERENCES_KEY])
    print(f"type(result[0]): {type(result[0])}")
    print(f"result[0].__class__.__name__: {result[0].__class__.__name__}")
    assert isinstance(result, list), f"Expected result type to be list, but got '{type(result)}'"
    assert len(result) == _EXPECTED_FORMAT_PREFERENCE_LENGTH, (
        f"Expected RedFormat list to contain {_EXPECTED_FORMAT_PREFERENCE_LENGTH} elements, but found {len(result)}"
    )
    assert all([isinstance(elem, RedFormat) for elem in result]), "Expected all elements to be of class 'RedFormat'"
    for i, actual_format in enumerate(result):
        expected_format = expected_red_format_list[i]
        assert actual_format == expected_format, (
            f"Unexpected RedFormat mismatch on {i}'th element of RedFormats list: expected: {expected_format}, actual: {actual_format}"
        )


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
    mock_format_prefs_config_data: list[dict[str, Any]], exception: Exception, exception_msg: str
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
                "lfm_api_key": "5678alsonotarealapikey",
                "lfm_username": "fake-username",
                "lfm_password": "fake-password",
            },
        ),
        (
            {"red_api_key": "cli-override-red-api-key"},
            {
                "red_api_key": "cli-override-red-api-key",
                "lfm_api_key": "5678alsonotarealapikey",
                "lfm_username": "fake-username",
                "lfm_password": "fake-password",
            },
        ),
        (
            {"lfm_api_key": "cli-override-lfm-api-key"},
            {
                "red_api_key": "1234notarealapikey",
                "lfm_api_key": "cli-override-lfm-api-key",
                "lfm_username": "fake-username",
                "lfm_password": "fake-password",
            },
        ),
        (
            {"lfm_username": "cli-override-lfm-username"},
            {
                "red_api_key": "1234notarealapikey",
                "lfm_api_key": "5678alsonotarealapikey",
                "lfm_username": "cli-override-lfm-username",
                "lfm_password": "fake-password",
            },
        ),
        (
            {"lfm_password": "cli-override-lfm-password"},
            {
                "red_api_key": "1234notarealapikey",
                "lfm_api_key": "5678alsonotarealapikey",
                "lfm_username": "fake-username",
                "lfm_password": "cli-override-lfm-password",
            },
        ),
    ],
)
def test_app_config_constructor(
    valid_config_filepath: str,
    minimal_valid_config_filepath: str,
    cli_params: dict[str, Any],
    expected_opts_vals: dict[str, Any],
) -> None:
    # test the construction from the full valid config file
    app_config = AppConfig(config_filepath=valid_config_filepath, cli_params=cli_params)
    for opt_key, expected_value in expected_opts_vals.items():
        actual_value = app_config.get_cli_option(opt_key)
        assert actual_value == expected_value, (
            f"Unexpected '{opt_key}' value: '{actual_value}'. Expected '{expected_value}'"
        )
    # test the construction from the minimal valid config file
    app_config = AppConfig(config_filepath=minimal_valid_config_filepath, cli_params=cli_params)
    for opt_key, expected_value in expected_opts_vals.items():
        actual_value = app_config.get_cli_option(opt_key)
        assert actual_value == expected_value, (
            f"Unexpected '{opt_key}' value: '{actual_value}'. Expected '{expected_value}'"
        )


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
    config_filepath: str, cli_params: dict[str, Any], exception_type: Exception, exception_msg: str
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
    final_cli_options_overrides: dict[str, Any],
    should_fail: bool,
    exception: Exception | None,
    exception_msg: str | None,
) -> None:
    mock_final_cli_options = {**valid_app_config.get_all_options(), **final_cli_options_overrides}
    valid_app_config._cli_options = mock_final_cli_options
    if should_fail:
        with pytest.raises(exception, match=exception_msg):
            valid_app_config._validate_final_cli_options()
    else:
        valid_app_config._validate_final_cli_options()


def test_get_root_summary_directory_path(valid_config_filepath: str, valid_app_config: AppConfig) -> None:
    expected = os.path.join(os.path.dirname(valid_config_filepath), _SUMMARIES_DIRNAME)
    actual = valid_app_config.get_root_summary_directory_path()
    assert actual == expected


@pytest.mark.parametrize("date_str_provided", [False, True])
def test_get_output_summary_dir_path(
    valid_config_filepath: str, valid_app_config: AppConfig, mock_run_date_str: str, date_str_provided: bool
) -> None:
    valid_app_config._run_datestr = mock_run_date_str
    if not date_str_provided:
        expected = os.path.join(os.path.dirname(valid_config_filepath), _SUMMARIES_DIRNAME, mock_run_date_str)
        actual = valid_app_config.get_output_summary_dir_path()
    else:
        date_str_arg = "2024-01-01__00-10-45"
        expected = os.path.join(os.path.dirname(valid_config_filepath), _SUMMARIES_DIRNAME, date_str_arg)
        actual = valid_app_config.get_output_summary_dir_path(date_str=date_str_arg)
    assert actual == expected


def test_pretty_print_config(valid_config_filepath: str) -> None:
    with patch("yaml.dump") as mock_yaml_dump:
        with patch.object(AppConfig, "_pretty_print_format_preferences") as mock_pretty_print_format_preferences:
            mock_pretty_print_format_preferences.return_value = None
            app_config = AppConfig(config_filepath=valid_config_filepath, cli_params=dict())
            app_config.pretty_print_config()
            mock_yaml_dump.assert_called_once()
            mock_pretty_print_format_preferences.assert_called_once()


def test_pretty_print_format_preferences(valid_config_filepath: str) -> None:
    with patch("yaml.dump") as mock_yaml_dump:
        app_config = AppConfig(config_filepath=valid_config_filepath, cli_params=dict())
        app_config._pretty_print_format_preferences()
        mock_yaml_dump.assert_called_once()


# TODO: add unit tests to ensure the jsonschema validation raises exceptions when expected
