import logging
import os
import re
import sys
from collections import Counter
from datetime import datetime
from functools import reduce
from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource

from plastered.config.field_validators import (
    APIRetries,
    CLIOverrideSetting,
    NonRedCallWait,
    RedCallWait,
    ValidRedEncoding,
    ValidRedFormat,
    ValidRedMedia,
    validate_cd_extras_log_value,
    validate_rec_types_to_scrape,
)
from plastered.utils.constants import CACHE_DIRNAME, RUN_DATE_STR_FORMAT, SUMMARIES_DIRNAME
from plastered.utils.exceptions import AppConfigException
from plastered.utils.red_utils import MediaEnum

_LOGGER = logging.getLogger(__name__)

_CD_EXTRAS_PRETTY_PRINT_REGEX_PATTERN = re.compile(r"^haslog=([0-9]+)&hascue=([0-9]+)$")


class SearchConfig(BaseModel):
    """RED search settings defined in the plastered config at `red.search`."""

    model_config = ConfigDict(frozen=True, validate_default=True, extra="ignore")
    use_release_type: bool = Field(default=True)
    use_first_release_year: bool = Field(default=True)
    use_record_label: bool = Field(default=False)
    use_catalog_number: bool = Field(default=False)
    enable_api_cache: bool = Field(default=True)


class SnatchesConfig(BaseModel):
    """RED snatch settings defined in the plastered config at `red.snatches`."""

    model_config = ConfigDict(frozen=True, validate_default=True, extra="ignore")
    snatch_directory: Path
    snatch_recs: bool
    max_size_gb: float = Field(ge=0.02, le=100.0)
    skip_prior_snatches: bool = Field(default=True)
    use_fl_tokens: bool = Field(default=False)
    min_allowed_ratio: float = Field(default=-1.0)


class CdOnlyExtras(BaseModel):
    """RED settings defined for a `red.format_preferences.cd_only_extras` entry in the plasterd yaml config."""

    log: int
    has_cue: bool

    # model_config = ConfigDict(validate_default=True)
    model_config = ConfigDict(frozen=True, validate_default=True, extra="ignore")

    @model_validator(mode="after")
    def post_model_validator(self) -> "CdOnlyExtras":
        validate_cd_extras_log_value(self.log)
        return self


class FormatPreference(BaseModel):
    """RED settings entry for a `red.format_preferences` entry in the plasterd yaml config."""

    model_config = ConfigDict(frozen=True, validate_default=True, extra="ignore")
    format: ValidRedFormat
    encoding: ValidRedEncoding
    media: ValidRedMedia
    cd_only_extras: CdOnlyExtras | None = None

    @model_validator(mode="after")
    def post_model_validator(self) -> Self:
        if self.media == MediaEnum.CD.value and self.cd_only_extras is None:
            raise ValueError(
                f"preference with media set to {MediaEnum.CD.value} must have a non-empty cd_only_extras field."
            )
        return self

    def get_yaml_dict_for_pretty_print(self) -> dict[str, Any]:
        entries = {"format": self.format, "encoding": self.encoding, "media": self.encoding}
        if self.cd_only_extras:
            log_str, cue_str = _CD_EXTRAS_PRETTY_PRINT_REGEX_PATTERN.findall(self.cd_only_extras)[0]
            entries["cd_only_extras"] = {"log": int(log_str), "has_cue": bool(int(cue_str))}
        return {"preference": entries}


class RedConfig(BaseModel):
    """App settings defined under the plastered yaml config's top-level `red` key."""

    model_config = ConfigDict(frozen=True, validate_default=True, extra="ignore")
    red_user_id: int = Field(gt=0)
    red_api_key: str = Field(min_length=1)
    red_api_retries: int = Field(ge=APIRetries.MIN.value, le=APIRetries.MAX.value, default=APIRetries.DEFAULT.value)
    red_api_seconds_between_calls: int = Field(
        ge=RedCallWait.MIN.value, le=RedCallWait.MAX.value, default=RedCallWait.DEFAULT.value
    )
    format_preferences: list[FormatPreference]
    snatches: SnatchesConfig
    search: SearchConfig | None = None

    @model_validator(mode="after")
    def post_model_validator(self) -> Self:
        if len(self.format_preferences) == 0:
            raise ValueError("format_preferences must have at least one entry.")
        fp_counter = Counter([str(fp) for fp in self.format_preferences])
        dupes = [str(fp) for fp, cnt in fp_counter.items() if cnt > 1]
        if len(dupes) > 0:
            raise ValueError(
                f"All entries in format_preferences must be unique. Following entries were duplicated: {dupes}"
            )
        return self


class LFMConfig(BaseModel):
    model_config = ConfigDict(frozen=True, validate_default=True, extra="ignore")
    lfm_api_key: str = Field(min_length=1)
    lfm_username: str = Field(min_length=1)
    lfm_password: str = Field(min_length=1)
    lfm_api_retries: int = Field(ge=APIRetries.MIN.value, le=APIRetries.MAX.value, default=APIRetries.DEFAULT.value)
    lfm_api_seconds_between_calls: int = Field(
        ge=NonRedCallWait.MIN.value, le=NonRedCallWait.MAX.value, default=NonRedCallWait.DEFAULT.value
    )
    rec_types_to_scrape: list[str] = Field(default_factory=lambda: ["album", "track"])
    scraper_max_rec_pages_to_scrape: int = Field(ge=1, le=5, default=5)
    allow_library_items: bool = Field(default=False)
    enable_scraper_cache: bool = Field(default=True)

    @model_validator(mode="after")
    def post_model_validator(self) -> Self:
        validate_rec_types_to_scrape(self.rec_types_to_scrape)
        return self


class MusicBrainzConfig(BaseModel):
    # TODO: rename this field to be consistent with the other `*_retries` fields.
    musicbrainz_api_max_retries: int = Field(
        ge=APIRetries.MIN.value, le=APIRetries.MAX.value, default=APIRetries.DEFAULT.value
    )
    musicbrainz_api_seconds_between_calls: int = Field(
        ge=NonRedCallWait.MIN.value, le=NonRedCallWait.MAX.value, default=NonRedCallWait.DEFAULT.value
    )

    # model_config = ConfigDict(validate_default=True)
    model_config = ConfigDict(frozen=True, validate_default=True, extra="ignore")


# TODO: change the config language to TOML
# TODO: add auto-documentation for the config files using this: https://github.com/radeklat/settings-doc
class AppSettings(BaseSettings):
    """Pydantic settings class encapsulating the `plastered` application yaml config."""

    model_config = SettingsConfigDict(frozen=True, extra="ignore")
    src_yaml_filepath: Path
    red: RedConfig
    lfm: LFMConfig
    musicbrainz: MusicBrainzConfig | None = None
    # Private, post-init attributes below
    _run_datestr: str
    _config_directory_path: Path
    _base_cache_directory_path: Path
    _root_summary_directory_path: Path

    def model_post_init(self, context: Any) -> None:
        """
        Assign derived, private instance attributes.
        https://docs.pydantic.dev/latest/concepts/models/#private-model-attributes
        """
        self._run_datestr = datetime.now().strftime(RUN_DATE_STR_FORMAT)
        self._config_directory_path = Path(os.path.dirname(os.path.abspath(self.src_yaml_filepath)))
        self._base_cache_directory_path = Path(os.path.join(self._config_directory_path, CACHE_DIRNAME))
        self._root_summary_directory_path = Path(os.path.join(self._config_directory_path, SUMMARIES_DIRNAME))

    def get(self, section: str, setting: str) -> Any:
        """Return the value for the specified config option, if it exists. Return `None` otherwise."""
        full_attr_path = f"{section}.{setting}"
        try:
            val = reduce(getattr, full_attr_path.split("."), self)
        except AttributeError:
            _LOGGER.warning(f"No such setting field named '{full_attr_path}'")
            return None
        return val

    def get_root_summary_directory_path(self) -> str:
        return self._root_summary_directory_path

    def get_output_summary_dir_path(self, date_str: str | None = None) -> str:
        if not date_str:
            return os.path.join(self._root_summary_directory_path, self._run_datestr)
        return os.path.join(self._root_summary_directory_path, date_str)

    def get_cache_directory_path(self, cache_type: str) -> str:
        return os.path.join(self._base_cache_directory_path, cache_type)

    def get_red_format_preferences(self) -> list[FormatPreference]:
        return self.red.format_preferences

    def is_cache_enabled(self, cache_type: str) -> None:
        if cache_type == "scraper":
            return self.lfm.enable_scraper_cache
        return self.red.search.enable_api_cache

    def pretty_print_config(self) -> None:
        yaml.dump(self.model_dump(), sys.stdout)


def get_app_settings(src_yaml_filepath: Path, cli_overrides: dict[str, Any] | None = None) -> AppSettings:
    """
    Returns the read-only `plastered` application settings configured by the yaml config plus any settings provided
    as options to the CLI. CLI options take precedence over the associated YAML settings.
    """
    settings_data = _get_settings_data(src_yaml_filepath=src_yaml_filepath, cli_overrides=cli_overrides)
    try:
        app_settings = AppSettings(**settings_data)
    except (ValidationError, ValueError) as ve:
        if isinstance(ve, ValidationError):
            _LOGGER.error(f"Invalid app config. Validation errors: {ve.errors()}")
            raise AppConfigException(
                "Invalid app config settings. See https://github.com/windexvalence/plastered/blob/main/docs/configuration_reference.md"
            ) from ve
        _LOGGER.error("Invalid CLI overrides provided to app config.", exc_info=True)
        raise AppConfigException(
            "Invalid CLI overrides provided to app config. See https://github.com/windexvalence/plastered/blob/main/docs/configuration_reference.md"
        ) from ve
    return app_settings


def _get_settings_data(src_yaml_filepath: Path, cli_overrides: dict[str, Any]) -> dict[str, Any]:
    yaml_source = YamlConfigSettingsSource(AppSettings, yaml_file=src_yaml_filepath)
    yaml_data = yaml_source()
    yaml_data["src_yaml_filepath"] = src_yaml_filepath
    if cli_overrides:
        for raw_k, raw_v in cli_overrides.items():
            attr_path = CLIOverrideSetting[raw_k.upper()].value.split(".")
            reduce(lambda sd, k: sd[k], attr_path[:-1], yaml_data)[attr_path[-1]] = raw_v
    return yaml_data
