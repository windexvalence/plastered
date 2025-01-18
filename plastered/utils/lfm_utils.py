from typing import Any, Dict, Optional


class LFMAlbumInfo:
    """
    Utility class wrapping the results of the LFM API's album.getinfo endpoint.
    Used by the ReleaseSearcher when usage of the LFM API is required for resolving certain additional search fields.
    """

    def __init__(self, artist: str, album_name: str, lfm_url: str, release_mbid: Optional[str]):
        self._artist = artist
        self._album_name = album_name
        self._lfm_url = lfm_url
        self._release_mbid = release_mbid

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
        """Constructs an LFMAlbumInfo instance from the LFM API's album.getinfo endpoint JSON response."""
        return cls(
            artist=json_blob["artist"],
            release_mbid=json_blob["mbid"],
            album_name=json_blob["name"],
            lfm_url=json_blob["url"],
        )

    def get_artist(self) -> str:
        return self._artist

    def get_release_mbid(self) -> Optional[str]:
        return self._release_mbid

    def get_album_name(self) -> str:
        return self._album_name

    def get_lfm_url(self) -> str:
        return self._lfm_url


class LFMTrackInfo:
    """
    Utility class wrapping the results of the LFM API's track.getinfo endpoint.
    Used by the ReleaseSearcher when mapping a track rec to the release it originated from. 
    Also optionally used by the ReleaseSearcher when resolving certain additional search fields (i.e. catalog number)
    from musicbrainz is required by the user's config.
    """

    def __init__(self, artist: str, track_name: str, release_name: str, lfm_url: str, release_mbid: Optional[str]):
        self._artist = artist
        self._track_name = track_name
        self._release_name = release_name
        self._lfm_url = lfm_url
        self._release_mbid = release_mbid

    def __eq__(self, other) -> bool:
        if not isinstance(other, LFMTrackInfo):
            return False
        return (
            other.get_artist() == self._artist
            and other.get_track_name() == self._track_name
            and other.get_release_mbid() == self._release_mbid
            and other.get_release_name() == self._release_name
            and other.get_lfm_url() == self._lfm_url
        )

    def __str__(self) -> str:
        return str(vars(self))

    @classmethod
    def construct_from_api_response(cls, json_blob: Dict[str, Any]):
        """Constructs an LFMTrackInfo instance from the LFM API's track.getinfo endpoint JSON response."""
        release_json = json_blob["album"]
        return cls(
            artist=json_blob["artist"],
            track_name=json_blob["name"],
            release_mbid=release_json["mbid"],
            release_name=release_json["title"],
            lfm_url=json_blob["url"],
        )

    def get_artist(self) -> str:
        return self._artist
    
    def get_track_name(self) -> str:
        return self._track_name

    def get_release_mbid(self) -> Optional[str]:
        return self._release_mbid

    def get_release_name(self) -> str:
        return self._release_name

    def get_lfm_url(self) -> str:
        return self._lfm_url
