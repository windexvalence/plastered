import logging
import os
from pathlib import Path
from unittest.mock import patch

from fastapi.templating import Jinja2Templates
import pytest

from plastered.config.app_settings import AppSettings, FormatPreference, LFMConfig, RedSearchOverrides, get_app_settings
from plastered.models.types import EncodingEnum, FormatEnum, MediaEnum
from tests.conftest import INVALID_CONFIGS_DIR_PATH, MOCK_RESOURCES_DIR_PATH, PROJECT_ABS_PATH, ROOT_MODULE_ABS_PATH


_CONFIGS_DIRPATH = Path(os.path.join(ROOT_MODULE_ABS_PATH), "config")
_INIT_CONF_FILEPATH = _CONFIGS_DIRPATH / "init_conf.yaml"


def test_get_app_settings_from_init_conf() -> None:
    actual = get_app_settings(src_yaml_filepath=_INIT_CONF_FILEPATH)
    assert isinstance(actual, AppSettings)


_LFM_CONFIG_REQUIRED_KWARGS = {"lfm_api_key": "key", "lfm_username": "user", "lfm_password": "pass"}


@pytest.mark.parametrize("allow_library_items", [True, False])
def test_allow_library_items_emits_deprecation_warning(
    caplog: pytest.LogCaptureFixture, allow_library_items: bool
) -> None:
    with caplog.at_level(logging.WARNING, logger="plastered.config.app_settings"):
        LFMConfig(**_LFM_CONFIG_REQUIRED_KWARGS, allow_library_items=allow_library_items)
    assert "`lfm.allow_library_items` config option is deprecated" in caplog.text


def test_allow_library_items_unset_emits_no_deprecation_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="plastered.config.app_settings"):
        LFMConfig(**_LFM_CONFIG_REQUIRED_KWARGS)
    assert "allow_library_items" not in caplog.text


def test_with_red_overrides_none_returns_self(valid_app_settings: AppSettings) -> None:
    assert valid_app_settings.with_red_overrides(None) is valid_app_settings


def test_with_red_overrides_empty_keeps_config_values(valid_app_settings: AppSettings) -> None:
    """An overrides object with no set fields yields a copy whose red search/snatch values match the config."""
    merged = valid_app_settings.with_red_overrides(RedSearchOverrides())
    assert merged is not valid_app_settings
    assert merged.red.snatches.snatch_recs == valid_app_settings.red.snatches.snatch_recs
    assert merged.red.search.use_catalog_number == valid_app_settings.red.search.use_catalog_number
    assert merged.red.format_preferences == valid_app_settings.red.format_preferences


def test_with_red_overrides_applies_all_fields(valid_app_settings: AppSettings) -> None:
    fp = FormatPreference(format=FormatEnum.MP3, encoding=EncodingEnum.MP3_320, media=MediaEnum.WEB)
    overrides = RedSearchOverrides(
        format_preferences=[fp],
        use_release_type=False,
        use_first_release_year=False,
        use_record_label=True,
        use_catalog_number=True,
        fuzzy_search_enabled=True,
        snatch=True,
        max_size_gb=12.5,
        skip_prior_snatches=False,
        use_fl_tokens=True,
    )
    merged = valid_app_settings.with_red_overrides(overrides)
    assert merged.red.format_preferences == [fp]
    assert merged.red.search.use_release_type is False
    assert merged.red.search.use_first_release_year is False
    assert merged.red.search.use_record_label is True
    assert merged.red.search.use_catalog_number is True
    assert merged.red.search.fuzzy_search_enabled is True
    assert merged.red.snatches.snatch_recs is True
    assert merged.red.snatches.max_size_gb == 12.5
    assert merged.red.snatches.skip_prior_snatches is False
    assert merged.red.snatches.use_fl_tokens is True
    # `min_allowed_ratio` is not overridable (scraper-only setting); the config value always carries through.
    assert merged.red.snatches.min_allowed_ratio == valid_app_settings.red.snatches.min_allowed_ratio
