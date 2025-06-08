from plastered.utils.red_utils import EncodingEnum, FormatEnum, MediaEnum

# Top-level key constants
CLI_RED_KEY = "red"
CLI_LFM_KEY = "lfm"
CLI_MUSICBRAINZ_KEY = "musicbrainz"
CLI_SNATCHES_KEY = "snatches"
CLI_SEARCH_KEY = "search"
CLI_SNATCH_DIRECTORY_KEY = "snatch_directory"
ENABLE_SNATCHING_KEY = "snatch_recs"
REC_TYPES_TO_SCRAPE_KEY = "rec_types_to_scrape"
_DEFAULT_RETRIES = 3
NON_RED_DEFAULT_SECONDS_BETWEEN_CALLS = 2
DEFAULTS_DICT = {
    # RED API defaults
    "red_api_retries": _DEFAULT_RETRIES,
    "red_api_seconds_between_calls": 5,
    # LFM API / scraping defaults
    "lfm_api_retries": _DEFAULT_RETRIES,
    "lfm_api_seconds_between_calls": NON_RED_DEFAULT_SECONDS_BETWEEN_CALLS,
    "scraper_max_rec_pages_to_scrape": 5,
    "rec_types_to_scrape": ["album", "track"],
    "allow_library_items": False,
    "enable_scraper_cache": True,
    # MusicBrainz API defaults
    "musicbrainz_api_max_retries": _DEFAULT_RETRIES,
    "musicbrainz_api_seconds_between_calls": NON_RED_DEFAULT_SECONDS_BETWEEN_CALLS,
    # Search defaults
    "use_release_type": True,
    "use_first_release_year": True,
    "use_record_label": False,
    "use_catalog_number": False,
    "enable_api_cache": True,
    # RED snatching defaults
    "skip_prior_snatches": True,
    "use_fl_tokens": False,
    "min_allowed_ratio": -1.0,
}
FORMAT_PREFERENCES_KEY = "format_preferences"
EXPECTED_TOP_LEVEL_CLI_KEYS = set([CLI_RED_KEY, CLI_LFM_KEY, CLI_SNATCHES_KEY])
OPTIONAL_TOP_LEVEL_CLI_KEYS = set([CLI_SEARCH_KEY])
# Sub-key constants
PER_PREFERENCE_KEY = "preference"
FORMAT_KEY = "format"
ENCODING_KEY = "encoding"
MEDIA_KEY = "media"
CD_ONLY_EXTRAS_KEY = "cd_only_extras"
REQUIRED_PREFERENCE_KEYS = set([FORMAT_KEY, ENCODING_KEY, MEDIA_KEY])
# CD-only extras sub-key constants
LOG_KEY = "log"
LOG_ENUMS = [-1, 0, 1, 100]
CUE_KEY = "has_cue"

_RETRIES_SCHEMA = {"type": "integer", "minimum": 1, "maximum": 10, "default": _DEFAULT_RETRIES}
_SECONDS_BETWEEN_CALLS_SCHEMA = {
    "type": "integer",
    "minimum": 1,
    "maximum": 6,
    "default": NON_RED_DEFAULT_SECONDS_BETWEEN_CALLS,
}

required_schema = {
    "type": "object",
    "properties": {
        CLI_RED_KEY: {
            "type": "object",
            "properties": {
                "red_user_id": {"type": ["string", "integer"]},
                "red_api_key": {"type": "string"},
                "red_api_retries": _RETRIES_SCHEMA,
                "red_api_seconds_between_calls": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 10,
                    "default": DEFAULTS_DICT["red_api_seconds_between_calls"],
                },
            },
            "required": ["red_user_id", "red_api_key"],
        },
        CLI_LFM_KEY: {
            "type": "object",
            "properties": {
                "lfm_api_key": {"type": "string"},
                "lfm_username": {"type": "string"},
                "lfm_password": {"type": "string"},
                "lfm_api_retries": _RETRIES_SCHEMA,
                "lfm_api_seconds_between_calls": _SECONDS_BETWEEN_CALLS_SCHEMA,
                "scraper_max_rec_pages_to_scrape": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": DEFAULTS_DICT["scraper_max_rec_pages_to_scrape"],
                },
                REC_TYPES_TO_SCRAPE_KEY: {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 2,
                    "items": {"type": "string", "enum": ["album", "track"]},
                    "default": DEFAULTS_DICT[REC_TYPES_TO_SCRAPE_KEY],
                },
                "allow_library_items": {"type": "boolean", "default": DEFAULTS_DICT["allow_library_items"]},
                "enable_scraper_cache": {"type": "boolean", "default": DEFAULTS_DICT["enable_scraper_cache"]},
            },
            "required": ["lfm_api_key", "lfm_username", "lfm_password"],
        },
        CLI_MUSICBRAINZ_KEY: {
            "type": "object",
            "properties": {
                "musicbrainz_api_max_retries": _RETRIES_SCHEMA,
                "musicbrainz_api_seconds_between_calls": _SECONDS_BETWEEN_CALLS_SCHEMA,
            },
        },
        CLI_SEARCH_KEY: {
            "type": "object",
            "properties": {
                "use_release_type": {"type": "boolean", "default": DEFAULTS_DICT["use_release_type"]},
                "use_first_release_year": {"type": "boolean", "default": DEFAULTS_DICT["use_first_release_year"]},
                "use_record_label": {"type": "boolean", "default": DEFAULTS_DICT["use_record_label"]},
                "use_catalog_number": {"type": "boolean", "default": DEFAULTS_DICT["use_catalog_number"]},
                "enable_api_cache": {"type": "boolean", "default": DEFAULTS_DICT["enable_api_cache"]},
            },
        },
        CLI_SNATCHES_KEY: {
            "type": "object",
            "properties": {
                "snatch_directory": {"type": "string"},
                ENABLE_SNATCHING_KEY: {"type": "boolean"},
                "skip_prior_snatches": {"type": "boolean", "default": DEFAULTS_DICT["skip_prior_snatches"]},
                "max_size_gb": {
                    "type": "number",
                    "minimum": 0.02,  # 20MB minimum
                    "maximum": 100.0,  # 100GB maximum
                },
                "use_fl_tokens": {"type": "boolean", "default": DEFAULTS_DICT["use_fl_tokens"]},
                "min_allowed_ratio": {"type": "number", "default": DEFAULTS_DICT["min_allowed_ratio"]},
            },
            "required": ["snatch_directory", ENABLE_SNATCHING_KEY, "max_size_gb"],
        },
        FORMAT_PREFERENCES_KEY: {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    PER_PREFERENCE_KEY: {
                        "type": "object",
                        "properties": {
                            FORMAT_KEY: {"type": "string", "enum": [format_enum.value for format_enum in FormatEnum]},
                            ENCODING_KEY: {
                                "type": "string",
                                "enum": [encoding_enum.value for encoding_enum in EncodingEnum],
                            },
                            MEDIA_KEY: {"type": "string", "enum": [media_enum.value for media_enum in MediaEnum]},
                            CD_ONLY_EXTRAS_KEY: {
                                "type": "object",
                                "properties": {
                                    LOG_KEY: {"type": "integer", "enum": LOG_ENUMS},
                                    CUE_KEY: {"type": "boolean"},
                                },
                                "required": [LOG_KEY, CUE_KEY],
                            },
                        },
                        "if": {
                            "properties": {MEDIA_KEY: {"const": MediaEnum.CD.value}},
                            "required": [FORMAT_KEY, ENCODING_KEY, MEDIA_KEY],
                        },
                        "then": {"required": [FORMAT_KEY, ENCODING_KEY, MEDIA_KEY, CD_ONLY_EXTRAS_KEY]},
                        "else": {"required": [FORMAT_KEY, ENCODING_KEY, MEDIA_KEY]},
                    }
                },
            },
            "minItems": 1,
        },
    },
}


def get_sub_keys_from_top_level_keys() -> list[str]:
    """
    Utility function for config pretty-printing via the CLI.
    Returns a dict mapping the top-level config keys to their corresponding list of sub-keys.
    """
    return {
        top_level_key: required_schema["properties"][top_level_key]["properties"].keys()
        for top_level_key in EXPECTED_TOP_LEVEL_CLI_KEYS
    }
