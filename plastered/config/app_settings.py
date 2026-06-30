import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime
from functools import reduce
from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator
from pydantic.json_schema import SkipJsonSchema
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource

from plastered.models.field_validators import (
    APIRetries,
    CLIOverrideSetting,
    NonRedCallWait,
    RedCallWait,
    validate_rec_types_to_scrape,
)
from plastered.models.red_models import RedFormat
from plastered.models.types import MediaEnum
from plastered.utils.constants import CACHE_DIRNAME, DB_FILENAME, RUN_DATE_STR_FORMAT, SUMMARIES_DIRNAME
from plastered.utils.exceptions import AppConfigException

_LOGGER = logging.getLogger(__name__)


def load_init_config_template() -> str:  # pragma: no cover
    """
    Utility function to aid new users in initializing a minimal config.yaml skeleton via the CLI's init_config command.
    """
    init_conf_filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "init_conf.yaml")
    with open(init_conf_filepath) as f:
        raw_init_conf_lines = f.readlines()
    return "".join(raw_init_conf_lines)


class SearchConfig(BaseModel):
    """RED search settings defined in the plastered config at `red.search`."""

    model_config = ConfigDict(frozen=True, validate_default=True, extra="ignore", title="search")
    use_release_type: bool = Field(default=True)
    use_first_release_year: bool = Field(default=True)
    use_record_label: bool = Field(default=False)
    use_catalog_number: bool = Field(default=False)


class SnatchesConfig(BaseModel):
    """RED snatch settings defined in the plastered config at `red.snatches`."""

    model_config = ConfigDict(frozen=True, validate_default=True, extra="ignore", title="snatches")
    snatch_directory: Path
    snatch_recs: bool
    max_size_gb: float = Field(ge=0.02, le=100.0)
    skip_prior_snatches: bool = Field(default=True)
    use_fl_tokens: bool = Field(default=False)
    min_allowed_ratio: float = Field(default=-1.0)


class FormatPreference(RedFormat):
    """RED settings entry for a `red.format_preferences` entry in the plastered yaml config."""

    model_config = ConfigDict(frozen=True, validate_default=True, extra="ignore", title="format_preference")

    @model_validator(mode="after")
    def post_model_validator(self) -> Self:
        if self.media == MediaEnum.CD.value and self.cd_only_extras is None:
            raise ValueError(  # pragma: no cover
                f"preference with media set to {MediaEnum.CD.value} must have a non-empty cd_only_extras field."
            )
        return self


class RedSearchOverrides(BaseModel):
    """
    Per-request overrides for the ad-hoc release search flow. Every field is optional; any field left unset falls back
    to the corresponding value from the user's `red` config. These let an ad-hoc API request tune the RED search /
    snatch behavior (`red.format_preferences`, `red.search`, `red.snatches`) without mutating the global config or
    touching the shared, throttled API clients.

    Note: `snatch_directory` is intentionally NOT overridable — the download location is a server-side concern and must
    not be settable by a client.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", title="red_search_overrides")
    # red.format_preferences
    format_preferences: list[FormatPreference] | None = Field(default=None)
    # red.search
    use_release_type: bool | None = Field(default=None)
    use_first_release_year: bool | None = Field(default=None)
    use_record_label: bool | None = Field(default=None)
    use_catalog_number: bool | None = Field(default=None)
    # red.snatches
    snatch: bool | None = Field(default=None)
    max_size_gb: float | None = Field(default=None, ge=0.02, le=100.0)
    skip_prior_snatches: bool | None = Field(default=None)
    use_fl_tokens: bool | None = Field(default=None)
    min_allowed_ratio: float | None = Field(default=None)


def _default_red_search_config() -> SearchConfig:  # pragma: no cover
    return SearchConfig()


class RedConfig(BaseModel):
    """App settings defined under the plastered yaml config's top-level `red` key."""

    model_config = ConfigDict(frozen=True, validate_default=True, extra="ignore", title="red")
    red_user_id: int = Field(gt=0)
    red_api_key: SecretStr = Field(min_length=1)
    red_api_retries: int = Field(ge=APIRetries.MIN.value, le=APIRetries.MAX.value, default=APIRetries.DEFAULT.value)
    red_api_seconds_between_calls: int = Field(
        ge=RedCallWait.MIN.value, le=RedCallWait.MAX.value, default=RedCallWait.DEFAULT.value
    )
    format_preferences: list[FormatPreference]
    snatches: SnatchesConfig = Field(title="snatches")
    search: SearchConfig = Field(title="search", default_factory=_default_red_search_config)

    @model_validator(mode="after")
    def post_model_validator(self) -> Self:
        if len(self.format_preferences) == 0:  # pragma: no cover
            raise ValueError("format_preferences must have at least one entry.")
        fp_counter = Counter([str(fp) for fp in self.format_preferences])
        dupes = [str(fp) for fp, cnt in fp_counter.items() if cnt > 1]
        if len(dupes) > 0:  # pragma: no cover
            raise ValueError(
                f"All entries in format_preferences must be unique. Following entries were duplicated: {dupes}"
            )
        return self


class LFMConfig(BaseModel):
    model_config = ConfigDict(frozen=True, validate_default=True, extra="ignore", title="lfm")
    lfm_api_key: SecretStr = Field(min_length=1)
    lfm_username: str = Field(min_length=1)
    lfm_password: SecretStr = Field(min_length=1)
    lfm_api_retries: int = Field(ge=APIRetries.MIN.value, le=APIRetries.MAX.value, default=APIRetries.DEFAULT.value)
    lfm_api_seconds_between_calls: int = Field(
        ge=NonRedCallWait.MIN.value, le=NonRedCallWait.MAX.value, default=NonRedCallWait.DEFAULT.value
    )
    rec_types_to_scrape: list[str] = Field(default_factory=lambda: ["album", "track"])
    scraper_max_rec_pages_to_scrape: int = Field(ge=1, le=5, default=5)
    allow_library_items: bool = Field(default=False)

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
    model_config = ConfigDict(frozen=True, validate_default=True, extra="ignore", title="musicbrainz")


class CacheConfig(BaseModel):
    model_config = ConfigDict(title="cache")
    api_cache_enabled: bool = Field(default=True)
    scraper_cache_enabled: bool = Field(default=True)


class ServerConfig(BaseModel):
    """Config section for the plastered API server."""

    model_config = ConfigDict(title="server")
    host: str = Field(default="0.0.0.0")  # nosec: B104
    port: int = Field(default=80)
    log_level: str = Field(default="INFO")
    # Default to a single worker: RED's "<=1 request / red_api_seconds_between_calls" rate limit is enforced per
    # process (each worker has its own throttle clock), so multiple workers could collectively exceed it. One worker
    # keeps the limit globally correct; async I/O still handles concurrency fine for this workload.
    workers: int = Field(default=1)


def _default_music_brainz_config() -> MusicBrainzConfig:
    return MusicBrainzConfig()


def _default_cache_config() -> CacheConfig:
    return CacheConfig()


def _default_server_config() -> ServerConfig:
    return ServerConfig()


# TODO: change the config language to TOML
# TODO: add auto-documentation for the config files using this: https://github.com/radeklat/settings-doc
class AppSettings(BaseSettings):
    """Pydantic settings class encapsulating the `plastered` application yaml config."""

    model_config = SettingsConfigDict(frozen=True, extra="ignore", title="config")
    src_yaml_filepath: SkipJsonSchema[Path]
    red: RedConfig = Field(title="red")
    lfm: LFMConfig = Field(title="lfm")
    musicbrainz: MusicBrainzConfig = Field(title="musicbrainz", default_factory=_default_music_brainz_config)
    cache: CacheConfig = Field(title="cache", default_factory=_default_cache_config)
    server: ServerConfig = Field(title="server", default_factory=_default_server_config)
    # Private, post-init attributes below
    _run_datestr: str
    _config_directory_path: Path
    _base_cache_directory_path: Path
    _root_summary_directory_path: Path
    _db_filepath: Path

    def model_post_init(self, context: Any) -> None:
        """
        Assign derived, private instance attributes.
        https://docs.pydantic.dev/latest/concepts/models/#private-model-attributes
        """
        self._run_datestr = datetime.now().strftime(RUN_DATE_STR_FORMAT)
        self._config_directory_path = Path(os.path.dirname(os.path.abspath(self.src_yaml_filepath)))
        self._base_cache_directory_path = Path(os.path.join(self._config_directory_path, CACHE_DIRNAME))
        self._root_summary_directory_path = Path(os.path.join(self._config_directory_path, SUMMARIES_DIRNAME))
        self._db_filepath = Path(os.path.join(self._config_directory_path, DB_FILENAME))

    def get_db_filepath(self) -> str:
        return os.fspath(self._db_filepath)

    def get_cache_directory_path(self, cache_type: str) -> str:
        return os.path.join(self._base_cache_directory_path, cache_type)

    def get_red_format_preferences(self) -> list[FormatPreference]:
        return self.red.format_preferences

    def with_red_overrides(self, overrides: "RedSearchOverrides | None") -> "AppSettings":
        """
        Returns a copy of these settings with the provided ad-hoc `RedSearchOverrides` merged onto the `red.search`,
        `red.snatches`, and `red.format_preferences` settings. Returns `self` unchanged when `overrides` is `None` or
        carries no set fields. Only the search/snatch parameters change — the shared, throttled API clients are never
        rebuilt, so all per-API rate-limit invariants are preserved.
        """
        if overrides is None:
            return self
        search_updates = {
            "use_release_type": overrides.use_release_type,
            "use_first_release_year": overrides.use_first_release_year,
            "use_record_label": overrides.use_record_label,
            "use_catalog_number": overrides.use_catalog_number,
        }
        search = self.red.search.model_copy(update={k: v for k, v in search_updates.items() if v is not None})
        snatch_updates = {
            "snatch_recs": overrides.snatch,
            "max_size_gb": overrides.max_size_gb,
            "skip_prior_snatches": overrides.skip_prior_snatches,
            "use_fl_tokens": overrides.use_fl_tokens,
            "min_allowed_ratio": overrides.min_allowed_ratio,
        }
        snatches = self.red.snatches.model_copy(update={k: v for k, v in snatch_updates.items() if v is not None})
        red_updates: dict[str, Any] = {"search": search, "snatches": snatches}
        if overrides.format_preferences is not None:
            red_updates["format_preferences"] = overrides.format_preferences
        red = self.red.model_copy(update=red_updates)
        return self.model_copy(update={"red": red})

    def is_cache_enabled(self, cache_type: str) -> bool:
        if cache_type == "scraper":
            return self.cache.scraper_cache_enabled
        return self.cache.api_cache_enabled

    def pretty_print_config(self) -> None:  # pragma: no cover
        yaml.dump(self.model_dump(), sys.stdout)


def get_app_settings(src_yaml_filepath: Path | None = None, cli_overrides: dict[str, Any] | None = None) -> AppSettings:
    """
    Returns the read-only `plastered` application settings configured by the yaml config plus any settings provided
    as options to the CLI. CLI options take precedence over the associated YAML settings.
    """
    if not src_yaml_filepath:
        src_yaml_filepath = Path(os.environ["PLASTERED_CONFIG"])
    settings_data = _get_settings_data(src_yaml_filepath=src_yaml_filepath, cli_overrides=cli_overrides)
    try:
        app_settings = AppSettings(**settings_data)
    except (ValidationError, ValueError) as ve:  # pragma: no cover
        if isinstance(ve, ValidationError):
            formatted_validation_errors = json.dumps(json.loads(ve.json()), indent=2)
            _LOGGER.error(f"Invalid app config. Validation errors: {formatted_validation_errors}")
            raise AppConfigException(
                f"Invalid app config settings. See https://github.com/windexvalence/plastered/blob/main/docs/config_reference.md\n\n{formatted_validation_errors}"
            ) from ve
        _LOGGER.error("Invalid CLI overrides provided to app config.", exc_info=True)
        raise AppConfigException(
            "Invalid CLI overrides provided to app config. See https://github.com/windexvalence/plastered/blob/main/docs/config_reference.md"
        ) from ve
    return app_settings


def _get_settings_data(src_yaml_filepath: Path, cli_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    yaml_source = YamlConfigSettingsSource(AppSettings, yaml_file=src_yaml_filepath)
    yaml_data = yaml_source()
    yaml_data["src_yaml_filepath"] = src_yaml_filepath
    if cli_overrides:
        for raw_k, raw_v in cli_overrides.items():
            attr_path = CLIOverrideSetting[raw_k.upper()].value.split(".")
            reduce(lambda sd, k: sd[k], attr_path[:-1], yaml_data)[attr_path[-1]] = raw_v
    return yaml_data
