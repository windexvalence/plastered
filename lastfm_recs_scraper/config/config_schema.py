from lastfm_recs_scraper.utils.red_utils import EncodingEnum, FormatEnum, MediaEnum

# Top-level key constants
CLI_RED_KEY = "red"
CLI_LAST_FM_KEY = "last_fm"
CLI_MUSICBRAINZ_KEY = "musicbrainz"
CLI_SNATCHES_KEY = "snatches"
CLI_SEARCH_KEY = "search"
CLI_SNATCH_DIRECTORY_KEY = "snatch_directory"
_DEFAULT_RETRIES = 3
DEFAULTS_DICT = {
    "red_api_retries": _DEFAULT_RETRIES,
    "last_fm_api_retries": _DEFAULT_RETRIES,
    "musicbrainz_api_max_retries": _DEFAULT_RETRIES,
    "red_api_seconds_between_calls": 5,
    "scraper_max_rec_pages_to_scrape": 5,
    "scraper_allow_library_items": False,
    "skip_prior_snatches": True,
    "use_record_label": False,
    "use_catalog_number": False,
}
FORMAT_PREFERENCES_KEY = "format_preferences"
EXPECTED_TOP_LEVEL_CLI_KEYS = set(
    [
        CLI_RED_KEY,
        CLI_LAST_FM_KEY,
        CLI_MUSICBRAINZ_KEY,
        CLI_SNATCHES_KEY,
        CLI_SEARCH_KEY,
    ]
)
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
    "default": 2,
}

required_schema = {
    "type": "object",
    "properties": {
        CLI_RED_KEY: {
            "type": "object",
            "properties": {
                "red_api_key": {"type": "string"},
                "red_api_retries": _RETRIES_SCHEMA,
                "red_api_seconds_between_calls": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": DEFAULTS_DICT["red_api_seconds_between_calls"],
                },
            },
            "required": ["red_api_key"],
        },
        CLI_LAST_FM_KEY: {
            "type": "object",
            "properties": {
                "last_fm_api_key": {"type": "string"},
                "last_fm_username": {"type": "string"},
                "last_fm_password": {"type": "string"},
                "last_fm_api_retries": _RETRIES_SCHEMA,
                "last_fm_api_seconds_between_calls": _SECONDS_BETWEEN_CALLS_SCHEMA,
                "scraper_max_rec_pages_to_scrape": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": DEFAULTS_DICT["scraper_max_rec_pages_to_scrape"],
                },
                "scraper_allow_library_items": {
                    "type": "boolean",
                    "default": DEFAULTS_DICT["scraper_allow_library_items"],
                },
            },
            "required": [
                "last_fm_api_key",
                "last_fm_username",
                "last_fm_password",
            ],
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
                "use_release_type": {"type": "boolean"},
                "use_first_release_year": {"type": "boolean"},
                "use_record_label": {"type": "boolean", "default": DEFAULTS_DICT["use_record_label"]},
                "use_catalog_number": {"type": "boolean", "default": DEFAULTS_DICT["use_catalog_number"]},
                "output_summary_filepath": {"type": "string"},
            },
            "required": [
                "use_release_type",
                "use_first_release_year",
                "output_summary_filepath",
            ],
        },
        CLI_SNATCHES_KEY: {
            "type": "object",
            "properties": {
                "snatch_directory": {"type": "string"},
                "snatch_recs": {"type": "boolean"},
                "skip_prior_snatches": {"type": "boolean", "default": DEFAULTS_DICT["skip_prior_snatches"]},
                "max_size_gb": {"type": "number"},
            },
            "required": ["snatch_directory", "snatch_recs", "skip_prior_snatches", "max_size_gb"],
        },
        FORMAT_PREFERENCES_KEY: {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    PER_PREFERENCE_KEY: {
                        "type": "object",
                        "properties": {
                            FORMAT_KEY: {
                                "type": "string",
                                "enum": [format_enum.value for format_enum in FormatEnum],
                            },
                            ENCODING_KEY: {
                                "type": "string",
                                "enum": [encoding_enum.value for encoding_enum in EncodingEnum],
                            },
                            MEDIA_KEY: {
                                "type": "string",
                                "enum": [media_enum.value for media_enum in MediaEnum],
                            },
                            CD_ONLY_EXTRAS_KEY: {
                                "type": "object",
                                "properties": {
                                    LOG_KEY: {
                                        "type": "integer",
                                        "enum": LOG_ENUMS,
                                    },
                                    CUE_KEY: {"type": "boolean"},
                                },
                                "required": [LOG_KEY, CUE_KEY],
                            },
                        },
                        "if": {
                            "properties": {MEDIA_KEY: {"const": MediaEnum.CD.value}},
                            "required": [FORMAT_KEY, ENCODING_KEY, MEDIA_KEY],
                        },
                        "then": {
                            "required": [
                                FORMAT_KEY,
                                ENCODING_KEY,
                                MEDIA_KEY,
                                CD_ONLY_EXTRAS_KEY,
                            ],
                        },
                        "else": {"required": [FORMAT_KEY, ENCODING_KEY, MEDIA_KEY]},
                    },
                },
            },
            "minItems": 1,
        },
    },
}
