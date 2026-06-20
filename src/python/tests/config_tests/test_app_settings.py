from datetime import datetime
import os
from pathlib import Path
from unittest.mock import patch

from fastapi.templating import Jinja2Templates
import pytest

from plastered.config.app_settings import AppSettings, get_app_settings
from plastered.utils.constants import RUN_DATE_STR_FORMAT
from tests.conftest import INVALID_CONFIGS_DIR_PATH, MOCK_RESOURCES_DIR_PATH, PROJECT_ABS_PATH, ROOT_MODULE_ABS_PATH


_CONFIGS_DIRPATH = Path(os.path.join(ROOT_MODULE_ABS_PATH), "config")
_INIT_CONF_FILEPATH = _CONFIGS_DIRPATH / "init_conf.yaml"
_SUMMARIES_DIRNAME = "summaries"


def test_get_app_settings_from_init_conf() -> None:
    actual = get_app_settings(src_yaml_filepath=_INIT_CONF_FILEPATH)
    assert isinstance(actual, AppSettings)
