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
_EXAMPLE_CONF_FILEPATH = Path(os.path.join(PROJECT_ABS_PATH, "examples", "config.yaml"))
_SUMMARIES_DIRNAME = "summaries"


def test_get_app_settings_from_init_conf() -> None:
    actual = get_app_settings(src_yaml_filepath=_INIT_CONF_FILEPATH)
    assert isinstance(actual, AppSettings)


@pytest.fixture(scope="session")
def settings_fixture() -> AppSettings:
    return get_app_settings(src_yaml_filepath=_EXAMPLE_CONF_FILEPATH)


@pytest.mark.parametrize(
    "section, setting",
    [
        ("red", "red_user_id"),
        ("red", "search.use_catalog_number"),
        ("red", "snatches.max_size_gb"),
        ("red", "format_preferences"),
        ("lfm", "lfm_username"),
        ("musicbrainz", "musicbrainz_api_max_retries"),
    ],
)
def test_app_settings_get(settings_fixture: AppSettings, section: str, setting: str) -> None:
    """Tests the `get` method for AppSettings works properly for valid lookups."""
    actual = settings_fixture.get(section=section, setting=setting)
    assert actual is not None


# def test_app_settings_get_error() -> None:
#     """Tests the `get` method for AppSettings properly handles errors for bad lookups."""
#     pass  # TODO: implement
