from typing import Final

RED_API_BASE_URL: Final[str] = "https://redacted.sh/ajax.php"
LFM_API_BASE_URL: Final[str] = "https://ws.audioscrobbler.com/2.0/"
MUSICBRAINZ_API_BASE_URL: Final[str] = "https://musicbrainz.org/ws/2/"

RED_JSON_RESPONSE_KEY: Final[str] = "response"

CACHE_DIRNAME: Final[str] = "cache"
DB_FILENAME: Final[str] = "plastered.db"
CACHE_TYPE_API: Final[str] = "api"
CACHE_TYPE_SCRAPER: Final[str] = "scraper"

PERMITTED_RED_API_ENDPOINTS: Final[frozenset[str]] = frozenset(
    ["browse", "torrentgroup", "community_stats", "user_torrents", "user"]
)
NON_CACHED_RED_API_ENDPOINTS: Final[frozenset[str]] = frozenset(["community_stats", "user_torrents", "user"])

PERMITTED_RED_SNATCH_API_ENDPOINTS: Final[frozenset[str]] = frozenset(["download"])
NON_CACHED_RED_SNATCH_API_ENDPOINTS: Final[frozenset[str]] = frozenset(["download"])

PERMITTED_LFM_API_ENDPOINTS: Final[frozenset[str]] = frozenset(["album.getinfo", "track.getinfo"])
PERMITTED_MUSICBRAINZ_API_ENDPOINTS: Final[frozenset[str]] = frozenset(["release", "recording"])

RENDER_WAIT_SEC_MIN: Final[int] = 3
RENDER_WAIT_SEC_MAX: Final[int] = 7

PW_USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.28 Mobile Safari/537.36"
)

ALBUM_RECS_BASE_URL: Final[str] = "https://www.last.fm/music/+recommended/albums"
ALBUM_REC_LIST_ELEMENT_CSS_SELECTOR: Final[str] = ".music-recommended-albums-item-name"
ALBUM_REC_LIST_ELEMENT_BS4_CSS_SELECTOR: Final[str] = ".music-recommended-albums-item-name a.link-block-target"
ALBUM_REC_CONTEXT_BS4_CSS_SELECTOR: Final[str] = "p.music-recommended-albums-album-context"

TRACK_RECS_BASE_URL: Final[str] = "https://www.last.fm/music/+recommended/tracks"
TRACK_REC_LIST_ELEMENT_CSS_SELECTOR: Final[str] = ".recommended-tracks-item-name"
TRACK_REC_LIST_ELEMENT_BS4_CSS_SELECTOR: Final[str] = ".recommended-tracks-item-name a.link-block-target"
TRACK_REC_CONTEXT_CSS_SELECTOR: Final[str] = "p.recommended-tracks-item-aux-text.recommended-tracks-item-context"

LOGIN_URL: Final[str] = "https://www.last.fm/login"
LOGIN_USERNAME_FORM_LOCATOR: Final[str] = "[name='username_or_email']"
LOGIN_PASSWORD_FORM_LOCATOR: Final[str] = "[name='password']"
LOGIN_BUTTON_LOCATOR: Final[str] = "[name='submit']"
LOGOUT_URL: Final[str] = "https://www.last.fm/logout"

STORAGE_UNIT_IDENTIFIERS: Final[frozenset[str]] = frozenset(["B", "MB", "GB"])
BYTES_IN_GB: Final[float] = 1e9
BYTES_IN_MB: Final[float] = 1e6

# Constant query params appended to every RED browse request. `filter_cat[1]=1` restricts results to the Music category.
RED_BROWSE_CONSTANT_PARAMS: Final[str] = "filter_cat[1]=1&group_results=1&order_by=seeders&order_way=desc"

# User-specified params to optionally append to the RED browse requests
RED_PARAM_RELEASE_TYPE: Final[str] = "releasetype"
RED_PARAM_RELEASE_YEAR: Final[str] = "year"
RED_PARAM_RECORD_LABEL: Final[str] = "recordlabel"
RED_PARAM_CATALOG_NUMBER: Final[str] = "cataloguenumber"

OPTIONAL_RED_PARAMS: Final[list[str]] = [
    RED_PARAM_RELEASE_TYPE,
    RED_PARAM_RELEASE_YEAR,
    RED_PARAM_RECORD_LABEL,
    RED_PARAM_CATALOG_NUMBER,
]

CLI_ALL_CACHE_TYPES: Final[str] = "@all"
API_ALL_CACHE_TYPES: Final[str] = "all"
