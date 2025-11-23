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


@pytest.mark.parametrize("date_str_provided", [False, True])
def test_get_output_summary_dir_path(date_str_provided: bool) -> None:
    mock_run_datetime = datetime(year=2025, month=12, day=31)
    mock_run_date_str = mock_run_datetime.strftime(RUN_DATE_STR_FORMAT)
    with patch("plastered.config.app_settings.datetime", wraps=datetime) as mock_datetime:
        mock_datetime.now.return_value = mock_run_datetime
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
        app_settings = get_app_settings(src_yaml_filepath=_EXAMPLE_CONF_FILEPATH)
        summary_path_str = os.fspath(app_settings._root_summary_directory_path)
        if not date_str_provided:
            expected = os.path.join(os.path.dirname(summary_path_str), _SUMMARIES_DIRNAME, mock_run_date_str)
            actual = app_settings.get_output_summary_dir_path()
        else:
            date_str_arg = "2024-01-01__00-10-45"
            expected = os.path.join(os.path.dirname(summary_path_str), _SUMMARIES_DIRNAME, date_str_arg)
            actual = app_settings.get_output_summary_dir_path(date_str=date_str_arg)
    assert actual == expected


# def test_app_settings_get_error() -> None:
#     """Tests the `get` method for AppSettings properly handles errors for bad lookups."""
#     pass  # TODO: implement
