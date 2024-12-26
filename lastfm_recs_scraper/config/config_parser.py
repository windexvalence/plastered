import os
import sys
import traceback
from typing import Any, Dict, List

import jsonschema
import yaml

from config.config_schema import (
    CD_ONLY_EXTRAS_KEY,
    CUE_KEY,
    ENCODING_KEY,
    EXPECTED_TOP_LEVEL_CLI_KEYS,
    FORMAT_KEY,
    FORMAT_PREFERENCES_KEY,
    LOG_KEY,
    MEDIA_KEY,
    PER_PREFERENCE_KEY,
    REQUIRED_PREFERENCE_KEYS,
    required_schema
)
from utils.exceptions import AppConfigException
from utils.logging_utils import get_custom_logger
from utils.red_utils import RedFormat, EncodingEnum, FormatEnum, MediaEnum


_LOGGER = get_custom_logger(__name__)


def _get_cd_only_extras_string(cd_only_extras_conf_data: Dict[str, str]) -> str:
    log_value = cd_only_extras_conf_data[LOG_KEY]
    log_value = "-1" if log_value <= 0 else log_value
    cue_value = int(cd_only_extras_conf_data[CUE_KEY])
    return f"haslog={log_value}&hascue={cue_value}"


def _load_red_formats_from_config(format_prefs_config_data: List[Dict[str, Any]]) -> List[RedFormat]:
    red_formats = []
    for pref in format_prefs_config_data:
        pref_dict = pref[PER_PREFERENCE_KEY]
        if not REQUIRED_PREFERENCE_KEYS.issubset(set(pref_dict.keys())):
            raise AppConfigException(f"Missing one or more required keys in the {FORMAT_PREFERENCES_KEY} configuration: {','.join(REQUIRED_PREFERENCE_KEYS)}. Only found keys: {pref_dict.keys()}")
        media = pref_dict[MEDIA_KEY]
        cd_only_extras_str = ""
        if media == MediaEnum.CD.value:
            if CD_ONLY_EXTRAS_KEY not in pref_dict:
                raise AppConfigException(f"Missing required '{CD_ONLY_EXTRAS_KEY}' setting for format preference entry with media type '{MediaEnum.CD.value}'.")
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
    if total_red_formats == 0:
        raise AppConfigException(f"Invalid '{FORMAT_PREFERENCES_KEY}' configuration: must have at least 1 entry in the '{FORMAT_PREFERENCES_KEY}' array.")
    unique_red_formats_count = len(set(red_formats))
    if unique_red_formats_count < total_red_formats:
        raise AppConfigException(f"Invalid '{FORMAT_PREFERENCES_KEY}' configuration: duplicate entries found, when each array element must be unique.")
    return red_formats


class AppConfig(object):
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
        for cli_key, cli_val in cli_params.items():
            if cli_val is not None and cli_key in self._cli_options.keys():
                _LOGGER.warning(f"CLI option '{cli_key}' provided and will override the value found in the provided config file ({config_filepath}).")
            self._cli_options[cli_key] = cli_val
        self._red_preference_ordering = _load_red_formats_from_config(format_prefs_config_data=raw_config_data[FORMAT_PREFERENCES_KEY])
    
    def get_cli_option(self, option_key: str) -> Any:
        return self._cli_options[option_key]

    def pretty_print_config(self) -> None:
        yaml.dump(self._cli_options, sys.stdout)
    
    def pretty_print_preference_ordering(self) -> None:
        output_lines = [str(pref) for pref in self._red_preference_ordering]
        yaml.dump(output_lines, sys.stdout)
    
    def get_red_preference_ordering(self) -> List[RedFormat]:
        return self._red_preference_ordering
