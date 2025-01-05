import os
import sys
import traceback
from collections import Counter
from typing import Any, Dict, List

import jsonschema
import yaml

from lastfm_recs_scraper.config.config_schema import (
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
    PER_PREFERENCE_KEY,
    required_schema,
)
from lastfm_recs_scraper.utils.exceptions import AppConfigException
from lastfm_recs_scraper.utils.logging_utils import get_custom_logger
from lastfm_recs_scraper.utils.red_utils import (
    EncodingEnum,
    FormatEnum,
    MediaEnum,
    RedFormat,
)

_LOGGER = get_custom_logger(__name__)


def load_init_config_template() -> str:
    """
    Utility function to aid new users in initializing a minimal config.yaml skeleton via the CLI's init_config command.
    """
    init_conf_filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "init_conf.yaml")
    with open(init_conf_filepath, "r") as f:
        raw_init_conf_lines = f.readlines()
    return "".join(raw_init_conf_lines)


def _get_cd_only_extras_string(cd_only_extras_conf_data: Dict[str, str]) -> str:
    log_value = cd_only_extras_conf_data[LOG_KEY]
    cue_value = int(cd_only_extras_conf_data[CUE_KEY])
    return f"haslog={log_value}&hascue={cue_value}"


def _load_red_formats_from_config(format_prefs_config_data: List[Dict[str, Any]]) -> List[RedFormat]:
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

    def __init__(self, config_filepath: str, cli_params: Dict[str, Any]):
        if not os.path.exists(config_filepath):
            raise AppConfigException(f"Provided config filepath does not exist: '{config_filepath}'")
        self._config_filepath = config_filepath
        self._cli_options = dict()
        with open(self._config_filepath, "r") as f:
            raw_config_data = yaml.safe_load(f.read())
        # Allow for explicit click CLI params to override the values in the config file.
        try:
            jsonschema.validate(instance=raw_config_data, schema=required_schema)
        except jsonschema.exceptions.ValidationError:
            raise AppConfigException(f"Provided yaml configuration's schema is invalid: {traceback.format_exc()}")
        for top_key in EXPECTED_TOP_LEVEL_CLI_KEYS:
            for option_key, option_value in raw_config_data[top_key].items():
                self._cli_options[option_key] = option_value
        # Set defaults for any fields which allow defaults and are not present in the config file
        for field_name, default_val in DEFAULTS_DICT.items():
            if field_name not in self._cli_options.keys():
                self._cli_options[field_name] = default_val
        # Any CLI options provided explicitly take precedence over the values in the config or the default values.
        for cli_key, cli_val in cli_params.items():
            if cli_val is not None and cli_key in self._cli_options.keys():
                _LOGGER.warning(
                    f"CLI option '{cli_key}' provided and will override the value found in the provided config file ({config_filepath})."
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
        if CLI_SNATCH_DIRECTORY_KEY in self._cli_options.keys():
            output_dir = self._cli_options[CLI_SNATCH_DIRECTORY_KEY]
            if not os.path.exists(output_dir) or not os.path.isdir(output_dir):
                raise AppConfigException(
                    f"Provided '{CLI_SNATCH_DIRECTORY_KEY}' value '{output_dir}' must exist and must be a directory."
                )

    def get_all_options(self) -> Dict[str, Any]:
        return self._cli_options

    def get_cli_option(self, option_key: str) -> Any:
        return self._cli_options[option_key]

    def pretty_print_config(self) -> None:
        yaml.dump(self._cli_options, sys.stdout)

    def pretty_print_preference_ordering(self) -> None:
        output_lines = [str(pref) for pref in self._red_preference_ordering]
        yaml.dump(output_lines, sys.stdout)

    def get_red_preference_ordering(self) -> List[RedFormat]:
        return self._red_preference_ordering
