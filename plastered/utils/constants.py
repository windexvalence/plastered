from typing import Final

RED_API_BASE_URL: Final[str] = "https://redacted.sh/ajax.php"
LFM_API_BASE_URL: Final[str] = "https://ws.audioscrobbler.com/2.0/"
MUSICBRAINZ_API_BASE_URL: Final[str] = "https://musicbrainz.org/ws/2/"

RED_JSON_RESPONSE_KEY: Final[str] = "response"

DB_FILENAME: Final[str] = "plastered.db"

RENDER_WAIT_SEC_MIN: Final[int] = 3
RENDER_WAIT_SEC_MAX: Final[int] = 7

PW_USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.28 Mobile Safari/537.36"
)

ALBUM_RECS_BASE_URL: Final[str] = "https://www.last.fm/music/+recommended/albums"
ALBUM_REC_LIST_ELEMENT_CSS_SELECTOR: Final[str] = ".music-recommended-albums-item-name"
ALBUM_REC_LIST_ELEMENT_BS4_CSS_SELECTOR: Final[str] = ".music-recommended-albums-item-name a.link-block-target"

TRACK_RECS_BASE_URL: Final[str] = "https://www.last.fm/music/+recommended/tracks"
TRACK_REC_LIST_ELEMENT_CSS_SELECTOR: Final[str] = ".recommended-tracks-item-name"
TRACK_REC_LIST_ELEMENT_BS4_CSS_SELECTOR: Final[str] = ".recommended-tracks-item-name a.link-block-target"

LOGIN_URL: Final[str] = "https://www.last.fm/login"
LOGIN_USERNAME_FORM_LOCATOR: Final[str] = "[name='username_or_email']"
LOGIN_PASSWORD_FORM_LOCATOR: Final[str] = "[name='password']"
LOGIN_BUTTON_LOCATOR: Final[str] = "[name='submit']"
LOGOUT_URL: Final[str] = "https://www.last.fm/logout"

STORAGE_UNIT_IDENTIFIERS: Final[frozenset[str]] = frozenset(["B", "MB", "GB"])
BYTES_IN_GB: Final[float] = 1e9
BYTES_IN_MB: Final[float] = 1e6

PLASTERED_CONFIG_ENVVAR: Final[str] = "PLASTERED_CONFIG"

# Keys for the optional release attributes attached to a `SearchItem` (from MusicBrainz resolution or an ad-hoc
# request) and applied client-side when matching RED release groups: release type and year act as filters, record
# label and catalogue number act as ranking signals. See `SearchState.get_candidate_release_groups`.
RED_PARAM_RELEASE_TYPE: Final[str] = "releasetype"
RED_PARAM_RELEASE_YEAR: Final[str] = "year"
RED_PARAM_RECORD_LABEL: Final[str] = "recordlabel"
RED_PARAM_CATALOG_NUMBER: Final[str] = "cataloguenumber"
