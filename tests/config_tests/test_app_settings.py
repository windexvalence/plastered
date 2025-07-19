import os
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from plastered.config.app_settings import AppSettings, get_app_settings
from tests.conftest import INVALID_CONFIGS_DIR_PATH, MOCK_RESOURCES_DIR_PATH, ROOT_MODULE_ABS_PATH


_INIT_CONF_FILEPATH = Path(os.path.join(ROOT_MODULE_ABS_PATH), "config", "init_conf.yaml")


def test_get_app_settings_from_init_conf() -> None:
    actual = get_app_settings(src_yaml_filepath=_INIT_CONF_FILEPATH)
    assert isinstance(actual, AppSettings)
    


def test_app_settings_get() -> None:
    """Tests the `get` method for AppSettings works properly for valid lookups."""
    actual = 


def test_app_settings_get_error() -> None:
    """Tests the `get` method for AppSettings properly handles errors for bad lookups."""
    pass  # TODO: implement
