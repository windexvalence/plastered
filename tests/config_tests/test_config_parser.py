import os
from itertools import product
from typing import Any, Dict, List

import pytest

from lastfm_recs_scraper.config.config_parser import (
    AppConfig,
    _get_cd_only_extras_string,
    _load_red_formats_from_config,
)
from lastfm_recs_scraper.config.config_schema import FORMAT_PREFERENCES_KEY
from lastfm_recs_scraper.utils.red_utils import RedFormat
from tests.conftest import (
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


# TODO: add unit tests to ensure the jsonschema validation raises exceptions when expected
