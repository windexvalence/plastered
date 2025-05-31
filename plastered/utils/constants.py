RED_API_BASE_URL = "https://redacted.sh/ajax.php"
LFM_API_BASE_URL = "https://ws.audioscrobbler.com/2.0/"
MUSICBRAINZ_API_BASE_URL = "https://musicbrainz.org/ws/2/"

RED_JSON_RESPONSE_KEY = "response"

CACHE_DIRNAME = "cache"
API_CACHE_DIRNAME = "api_cache"
SCRAPER_CACHE_DIRNAME = "scraper_cache"
CACHE_TYPE_API = "api"
CACHE_TYPE_SCRAPER = "scraper"

PERMITTED_RED_API_ENDPOINTS = set(["browse", "torrentgroup", "community_stats", "user_torrents", "user"])
NON_CACHED_RED_API_ENDPOINTS = set(["community_stats", "user_torrents", "user"])

PERMITTED_RED_SNATCH_API_ENDPOINTS = set(["download"])
NON_CACHED_RED_SNATCH_API_ENDPOINTS = set(["download"])

PERMITTED_LFM_API_ENDPOINTS = set(["album.getinfo", "track.getinfo"])
PERMITTED_MUSICBRAINZ_API_ENDPOINTS = set(["release", "recording"])

RENDER_WAIT_SEC_MIN = 3
RENDER_WAIT_SEC_MAX = 7

PW_USER_AGENT = "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.28 Mobile Safari/537.36"

ALBUM_RECS_BASE_URL = "https://www.last.fm/music/+recommended/albums"
ALBUM_REC_LIST_ELEMENT_CSS_SELECTOR = ".music-recommended-albums-item-name"
ALBUM_REC_LIST_ELEMENT_BS4_CSS_SELECTOR = ".music-recommended-albums-item-name a.link-block-target"
ALBUM_REC_CONTEXT_BS4_CSS_SELECTOR = "p.music-recommended-albums-album-context"

TRACK_RECS_BASE_URL = "https://www.last.fm/music/+recommended/tracks"
TRACK_REC_LIST_ELEMENT_CSS_SELECTOR = ".recommended-tracks-item-name"
TRACK_REC_LIST_ELEMENT_BS4_CSS_SELECTOR = ".recommended-tracks-item-name a.link-block-target"
TRACK_REC_CONTEXT_CSS_SELECTOR = "p.recommended-tracks-item-aux-text.recommended-tracks-item-context"

LOGIN_URL = "https://www.last.fm/login"
LOGIN_USERNAME_FORM_LOCATOR = "[name='username_or_email']"
LOGIN_PASSWORD_FORM_LOCATOR = "[name='password']"  # nosec B105
LOGIN_BUTTON_LOCATOR = "[name='submit']"
LOGOUT_URL = "https://www.last.fm/logout"

RUN_DATE_STR_FORMAT = "%Y-%m-%d__%H-%M-%S"

STORAGE_UNIT_IDENTIFIERS = ["B", "MB", "GB"]
BYTES_IN_GB = float(1e9)

# TODO: consolidate these
STATS_TRACK_REC_NONE = "N/A"
STATS_NONE = "N/A"
