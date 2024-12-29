import requests

from lastfm_recs_scraper.utils.http_utils import request_lastfm_api
from lastfm_recs_scraper.utils.logging_utils import get_custom_logger

_LOGGER = get_custom_logger(__name__)


class LastFMAlbumInfo(object):
    def __init__(self, artist: str, release_mbid: str, album_name: str, lastfm_url: str):
        self._artist = artist
        self._release_mbid = release_mbid
        self._album_name = album_name
        self._lastfm_url = lastfm_url

    def __eq__(self, other) -> bool:
        if not isinstance(other, LastFMAlbumInfo):
            return False
        return (
            other.get_artist() == self._artist
            and other.get_release_mbid() == self._release_mbid
            and other.get_album_name() == self._album_name
            and other.get_lastfm_url() == self._lastfm_url
        )

    def __str__(self) -> str:
        return str(vars(self))

    @classmethod
    def construct_from_api_response(
        cls,
        last_fm_api_key: str,
        last_fm_client: requests.Session,
        last_fm_artist_name: str,
        last_fm_album_name: str,
    ):
        json_blob = request_lastfm_api(
            last_fm_client=last_fm_client,
            method="album.getinfo",
            api_key=last_fm_api_key,
            params=f"artist={last_fm_artist_name}&album={last_fm_album_name}",
        )
        return cls(
            artist=json_blob["artist"],
            release_mbid=json_blob["mbid"],
            album_name=json_blob["name"],
            lastfm_url=json_blob["url"],
        )

    def get_artist(self) -> str:
        return self._artist

    def get_release_mbid(self) -> str:
        return self._release_mbid

    def get_album_name(self) -> str:
        return self._album_name

    def get_lastfm_url(self) -> str:
        return self._lastfm_url


# TODO (later): figure out if we should handle tracks?
