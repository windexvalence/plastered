from collections import Counter
from pathlib import Path
from typing import ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    YamlConfigSettingsSource,
    SettingsConfigDict,
)

from plastered.config.field_validators import APIRetries, NonRedCallWait, RedCallWait, ValidRedEncoding, ValidRedFormat, ValidRedMedia, validate_cd_extras_log_value, validate_rec_types_to_scrape
from plastered.utils.red_utils import MediaEnum


class SearchConfig(BaseModel):
    """RED search settings defined in the plastered config at `red.search`."""
    use_release_type: bool = Field(default=True)
    use_first_release_year: bool = Field(default=True)
    use_record_label: bool = Field(default=False)
    use_catalog_number: bool = Field(default=False)
    enable_api_cache: bool = Field(default=True)

    model_config = ConfigDict(frozen=True, validate_default=True)


class SnatchesConfig(BaseModel):
    """RED snatch settings defined in the plastered config at `red.snatches`."""
    snatch_directory: Path
    snatch_recs: bool
    max_size_gb: float = Field(ge=0.02, le=100.0)
    skip_prior_snatches: bool = Field(default=True)
    use_fl_tokens: bool = Field(default=False)
    min_allowed_ratio: float = Field(default=-1.0)

    model_config = ConfigDict(frozen=True, validate_default=True)


class CdOnlyExtras(BaseModel):
    """RED settings defined for a `red.format_preferences.cd_only_extras` entry in the plasterd yaml config."""
    log: int
    has_cue: bool

    model_config = ConfigDict(frozen=True, validate_default=True)

    @model_validator(mode="after")
    def post_model_validator(self) -> "CdOnlyExtras":
        validate_cd_extras_log_value(self.log)
        return self


class FormatPreference(BaseModel):
    """RED settings entry for a `red.format_preferences` entry in the plasterd yaml config."""
    format: ValidRedFormat
    encoding: ValidRedEncoding
    media: ValidRedMedia
    cd_only_extras: CdOnlyExtras | None = None

    model_config = ConfigDict(frozen=True, validate_default=True)

    @model_validator(mode="after")
    def post_model_validator(self) -> Self:
        if self.media == MediaEnum.CD.value and self.cd_only_extras is None:
            raise ValueError(
                f"preference with media set to {MediaEnum.CD.value} must have a non-empty cd_only_extras field."
            )
        return self


class RedConfig(BaseModel):
    """App settings defined under the plastered yaml config's top-level `red` key."""
    red_user_id: int = Field(gt=0)
    red_api_key: str = Field(min_length=1)
    red_api_retries: int = Field(ge=APIRetries.MIN.value, le=APIRetries.MAX.value, default=APIRetries.DEFAULT.value)
    red_api_seconds_between_calls: int = Field(
        ge=RedCallWait.MIN.value, le=RedCallWait.MAX.value, default=RedCallWait.DEFAULT.value
    )
    format_preferences: list[FormatPreference]
    snatches: SnatchesConfig
    search: SearchConfig | None = None

    model_config = ConfigDict(frozen=True, validate_default=True)

    @model_validator(mode="after")
    def post_model_validator(self) -> Self:
        if len(self.format_preferences) == 0:
            raise ValueError("format_preferences must have at least one entry.")
        if len(set(self.format_preferences)) != len(self.format_preferences):
            fp_counter = Counter(self.format_preferences)
            dupes = [str(fp) for fp, cnt in fp_counter.items() if cnt > 1]
            raise ValueError(
                f"All entries in format_preferences must be unique. Following entries were duplicated: {dupes}"
            )
        return self


class LFMConfig(BaseModel):
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

    model_config = ConfigDict(frozen=True, validate_default=True)

    @model_validator(mode="after")
    def post_model_validator(self) -> Self:
        validate_rec_types_to_scrape(self.rec_types_to_scrape)
        return self


class MusicBrainzConfig(BaseModel):
    # TODO: rename this field to be consistent with the other `*_retries` fields.
    musicbrainz_api_max_retries: int = Field(ge=APIRetries.MIN.value, le=APIRetries.MAX.value, default=APIRetries.DEFAULT.value)
    musicbrainz_api_seconds_between_calls: int = Field(
        ge=NonRedCallWait.MIN.value, le=NonRedCallWait.MAX.value, default=NonRedCallWait.DEFAULT.value
    )

    model_config = ConfigDict(frozen=True, validate_default=True)


class AppSettings(BaseSettings):
    """Pydantic settings class encapsulating the `plastered` application yaml config."""
    red: RedConfig
    lfm: LFMConfig
    musicbrainz: MusicBrainzConfig | None = None

    src_yaml_filepath: ClassVar[Path] = None
    model_config = SettingsConfigDict(frozen=True)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        sources = (init_settings, env_settings, dotenv_settings, file_secret_settings)
        if cls.src_yaml_filepath:
            sources = sources + (YamlConfigSettingsSource(settings_cls, yaml_file=cls.src_yaml_filepath),)
        return sources


class _AppSettingsSingleton:
    """Utility class for managing one `AppSettings` instance as a singleton."""
    _app_settings_inst: ClassVar[AppSettings | None] = None

    @classmethod
    def get_app_settings_inst(cls, src_yaml_filepath: Path) -> AppSettings:
        if cls._app_settings_inst is None:
            AppSettings.src_yaml_filepath = src_yaml_filepath
            cls._app_settings_inst = AppSettings()
        return cls._app_settings_inst


def get_app_settings(src_yaml_filepath: Path | None = Path("/config/config.yaml")) -> AppSettings:
    """Returns the singleton instance of the `plastered` application settings."""
    return _AppSettingsSingleton.get_app_settings_inst(src_yaml_filepath=src_yaml_filepath)


if __name__ == "__main__":
    # TODO: figure out how to override this path cleanly from user-provided CLI args / envvars
    AppSettings.src_yaml_filepath = "/config/config.yaml"  # default value
    current_settings = AppSettings()
    ``