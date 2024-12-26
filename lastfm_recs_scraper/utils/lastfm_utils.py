import requests

from utils.http_utils import request_lastfm_api
from utils.logging_utils import get_custom_logger


_LOGGER = get_custom_logger(__name__)


class LastFMAlbumInfo(object):
    def __init__(self, artist: str, release_mbid: str, album_name: str, lastfm_url: str):
        self._artist = artist
        self._release_mbid = release_mbid
        self._album_name = album_name
        self._lastfm_url = lastfm_url
    
    @classmethod
    def construct_from_api_response(cls, last_fm_api_key: str, last_fm_client: requests.Session, last_fm_artist_name: str, last_fm_album_name: str):
        json_blob = request_lastfm_api(last_fm_client=last_fm_client, method="album.getinfo", api_key=last_fm_api_key, params=f"artist={last_fm_artist_name}&album={last_fm_album_name}")
        return cls(
            artist=json_blob["artist"],
            release_mbid=json_blob["mbid"],
            album_name=json_blob["name"],
            lastfm_url=json_blob["url"],
        )
    
    def get_release_mbid(self) -> str:
        return self._release_mbid

    def get_lastfm_url(self) -> str:
        return self._lastfm_url

# TODO: figure out if we should handle tracks?
