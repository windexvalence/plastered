import logging
import os
import sys
import traceback
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

import jsonschema
import yaml

from plastered.config.config_schema import (
    CD_ONLY_EXTRAS_KEY,
    CLI_SNATCH_DIRECTORY_KEY,
    CUE_KEY,
    DEFAULTS_DICT,
    ENCODING_KEY,
    EXPECTED_TOP_LEVEL_CLI_KEYS,
    FORMAT_KEY,
    FORMAT_PREFERENCES_KEY,
    LOG_KEY,
    MEDIA_KEY,
    OPTIONAL_TOP_LEVEL_CLI_KEYS,
    PER_PREFERENCE_KEY,
    get_sub_keys_from_top_level_keys,
    required_schema,
)
from plastered.utils.constants import RUN_DATE_STR_FORMAT
from plastered.utils.exceptions import AppConfigException
from plastered.utils.red_utils import EncodingEnum, FormatEnum, MediaEnum, RedFormat


_LOGGER = logging.getLogger(__name__)
_CACHE_DIRNAME = "cache"
_SUMMARIES_DIRNAME = "summaries"


def load_init_config_template() -> str:
    """
    Utility function to aid new users in initializing a minimal config.yaml skeleton via the CLI's init_config command.
    """
    init_conf_filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "init_conf.yaml")
    with open(init_conf_filepath) as f:
        raw_init_conf_lines = f.readlines()
    return "".join(raw_init_conf_lines)


def _get_cd_only_extras_string(cd_only_extras_conf_data: dict[str, str]) -> str:
    log_value = cd_only_extras_conf_data[LOG_KEY]
    cue_value = int(cd_only_extras_conf_data[CUE_KEY])
    return f"haslog={log_value}&hascue={cue_value}"


def _load_red_formats_from_config(format_prefs_config_data: list[dict[str, Any]]) -> list[RedFormat]:
    red_formats = []
    for pref in format_prefs_config_data:
        pref_dict = pref[PER_PREFERENCE_KEY]
        media = pref_dict[MEDIA_KEY]
        cd_only_extras_str = ""
        if media == MediaEnum.CD.value:
            cd_only_extras_str = _get_cd_only_extras_string(pref_dict[CD_ONLY_EXTRAS_KEY])

        red_formats.append(
            RedFormat(
                format=FormatEnum(pref_dict[FORMAT_KEY]),
                encoding=EncodingEnum(pref_dict[ENCODING_KEY]),
                media=MediaEnum(media),
                cd_only_extras=cd_only_extras_str,
            )
        )
    total_red_formats = len(red_formats)
    unique_red_formats_count = len(set(red_formats))
    if unique_red_formats_count < total_red_formats:
        dupes = [item for item, count in Counter(red_formats).items() if count > 1]
        raise AppConfigException(
            f"Invalid '{FORMAT_PREFERENCES_KEY}' configuration: duplicate entries found ({[str(dupe) for dupe in dupes]}), but each array element must be unique."
        )
    return red_formats


class AppConfig:
    """
    Utility class for gathering and merging user-provided options from both the CLI and the configuration file.
    This class is the source of truth for the user's runtime configurations. Prioritizes CLI-based / env-var based options over the yaml config options.
    """

    def __init__(self, config_filepath: str, cli_params: dict[str, Any]):
        if not os.path.exists(config_filepath):
            raise AppConfigException(f"Provided config filepath does not exist: '{config_filepath}'")
        self._run_datestr = datetime.now().strftime(RUN_DATE_STR_FORMAT)
        self._config_filepath = config_filepath
        self._config_directory_path = os.path.dirname(os.path.abspath(config_filepath))
        self._base_cache_directory_path = os.path.join(self._config_directory_path, _CACHE_DIRNAME)
        self._root_summary_directory_path = os.path.join(self._config_directory_path, _SUMMARIES_DIRNAME)
        if not os.path.isdir(self._root_summary_directory_path):
            _LOGGER.info(f"{self._root_summary_directory_path} directory not found. Attempting to create ...")
            os.makedirs(self._root_summary_directory_path, 0o755)
        self._cli_options: dict[str, Any] = dict()
        with open(self._config_filepath) as f:
            raw_config_data = yaml.safe_load(f.read())
        # run basic schema validation on data loaded from config file
        try:
            jsonschema.validate(instance=raw_config_data, schema=required_schema)
        except jsonschema.exceptions.ValidationError as ex:
            raise AppConfigException(
                f"Provided yaml configuration's schema is invalid: {traceback.format_exc()}"
            ) from ex
        for top_key in EXPECTED_TOP_LEVEL_CLI_KEYS:
            for option_key, option_value in raw_config_data[top_key].items():
                self._cli_options[option_key] = option_value
        for optional_top_key in OPTIONAL_TOP_LEVEL_CLI_KEYS:
            if optional_top_key in raw_config_data:
                for option_key, option_value in raw_config_data[optional_top_key].items():
                    self._cli_options[option_key] = option_value
        # Set defaults for any fields which allow defaults and are not present in the config file
        for field_name, default_val in DEFAULTS_DICT.items():
            if field_name not in self._cli_options:
                self._cli_options[field_name] = default_val
        # Any CLI options provided explicitly take precedence over the values in the config or the default values.
        for cli_key, cli_val in cli_params.items():
            if cli_val is not None and cli_key in self._cli_options:
                _LOGGER.warning(
                    f"CLI/Env '{cli_key}' option provided will override the value found in the provided config file ({config_filepath})."
                )
                self._cli_options[cli_key] = cli_val

        self._validate_final_cli_options()
        self._red_preference_ordering = _load_red_formats_from_config(
            format_prefs_config_data=raw_config_data[FORMAT_PREFERENCES_KEY]
        )

    def _validate_final_cli_options(self) -> None:
        """
        Various per-option validations which don't fall under the jsonschema validations or required fields validations go here.
        Raises an AppConfigException if any validation condition is not met.
        """
        if CLI_SNATCH_DIRECTORY_KEY in self._cli_options:
            output_dir = self._cli_options[CLI_SNATCH_DIRECTORY_KEY]
            if not os.path.exists(output_dir) or not os.path.isdir(output_dir):
                raise AppConfigException(
                    f"Provided '{CLI_SNATCH_DIRECTORY_KEY}' value '{output_dir}' must exist and must be a directory."
                )

    def get_all_options(self) -> dict[str, Any]:
        return self._cli_options

    def get_cli_option(self, option_key: str) -> Any:
        return self._cli_options[option_key]

    def get_root_summary_directory_path(self) -> str:
        return self._root_summary_directory_path

    def get_output_summary_dir_path(self, date_str: str | None = None) -> str:
        if not date_str:
            return os.path.join(self._root_summary_directory_path, self._run_datestr)
        return os.path.join(self._root_summary_directory_path, date_str)

    def get_cache_directory_path(self, cache_type: str) -> str:
        return os.path.join(self._base_cache_directory_path, cache_type)

    def is_cache_enabled(self, cache_type: str) -> bool:
        return self.get_cli_option(f"enable_{cache_type}_cache")

    def _pretty_print_format_preferences(self) -> None:
        formatted_dict = {
            FORMAT_PREFERENCES_KEY: [pref.get_yaml_dict_for_pretty_print() for pref in self._red_preference_ordering]
        }
        yaml.dump(formatted_dict, sys.stdout)

    def pretty_print_config(self) -> None:
        top_level_keys_to_sub_keys = get_sub_keys_from_top_level_keys()
        pp_dict = defaultdict(dict)
        for top_level_key, sub_keys in top_level_keys_to_sub_keys.items():
            for sub_key in sub_keys:
                pp_dict[top_level_key][sub_key] = self._cli_options[sub_key]
        yaml.dump(dict(pp_dict), sys.stdout)
        self._pretty_print_format_preferences()

    def get_red_preference_ordering(self) -> list[RedFormat]:
        return self._red_preference_ordering
