from typing import Any, Dict


class LFMAlbumInfo:
    """
    Utility class wrapping the results of the LFM API's album.getinfo endpoint.
    Used by the ReleaseSearcher when usage of the LFM API is required for resolving certain additional search fields.
    """

    def __init__(self, artist: str, release_mbid: str, album_name: str, lfm_url: str):
        self._artist = artist
        self._release_mbid = release_mbid
        self._album_name = album_name
        self._lfm_url = lfm_url

    def __eq__(self, other) -> bool:
        if not isinstance(other, LFMAlbumInfo):
            return False
        return (
            other.get_artist() == self._artist
            and other.get_release_mbid() == self._release_mbid
            and other.get_album_name() == self._album_name
            and other.get_lfm_url() == self._lfm_url
        )

    def __str__(self) -> str:
        return str(vars(self))

    @classmethod
    def construct_from_api_response(cls, json_blob: Dict[str, Any]):
        return cls(
            artist=json_blob["artist"],
            release_mbid=json_blob["mbid"],
            album_name=json_blob["name"],
            lfm_url=json_blob["url"],
        )

    def get_artist(self) -> str:
        return self._artist

    def get_release_mbid(self) -> str:
        return self._release_mbid

    def get_album_name(self) -> str:
        return self._album_name

    def get_lfm_url(self) -> str:
        return self._lfm_url
