RED_API_BASE_URL = "https://redacted.sh/ajax.php"
LAST_FM_API_BASE_URL = "http://ws.audioscrobbler.com/2.0/"
MUSICBRAINZ_API_BASE_URL = "http://musicbrainz.org/ws/2/"

# TODO: permit addtocollage as action
PERMITTED_RED_API_ACTIONS = set(["browse", "download", "torrentgroup"])
PERMITTED_LAST_FM_API_METHODS = set(["album.getinfo", "track.getinfo"])
