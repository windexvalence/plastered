RED_API_BASE_URL = "https://redacted.sh/ajax.php"
LAST_FM_API_BASE_URL = "http://ws.audioscrobbler.com/2.0/"
MUSICBRAINZ_API_BASE_URL = "http://musicbrainz.org/ws/2/"

# TODO: permit addtocollage as action
PERMITTED_RED_API_ACTIONS = set(["browse", "download", "torrentgroup", "community_stats", "user_torrents"])
PERMITTED_LAST_FM_API_METHODS = set(["album.getinfo", "track.getinfo"])

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

STORAGE_UNIT_IDENTIFIERS = ["B", "MB", "GB"]
