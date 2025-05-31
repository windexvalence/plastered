from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class LFMAlbumInfo:
    """
    Utility class wrapping the results of the LFM API's album.getinfo endpoint.
    Used by the ReleaseSearcher when usage of the LFM API is required for resolving certain additional search fields.
    """

    artist: str
    album_name: str
    lfm_url: str
    release_mbid: Optional[str] = None

    @classmethod
    def construct_from_api_response(cls, json_blob: Dict[str, Any]):
        """Constructs an LFMAlbumInfo instance from the LFM API's album.getinfo endpoint JSON response."""
        return cls(
            artist=json_blob["artist"],
            release_mbid=json_blob["mbid"],
            album_name=json_blob["name"],
            lfm_url=json_blob["url"],
        )

    def get_release_mbid(self) -> Optional[str]:
        return self.release_mbid


@dataclass
class LFMTrackInfo:
    """
    Utility class wrapping the results of the LFM API's track.getinfo endpoint.
    Used by the ReleaseSearcher when mapping a track rec to the release it originated from.
    Also optionally used by the ReleaseSearcher when resolving certain additional search fields (i.e. catalog number)
    from musicbrainz is required by the user's config.
    """

    artist: str
    track_name: str
    release_name: str
    lfm_url: str
    release_mbid: Optional[str] = None

    @classmethod
    def construct_from_api_response(cls, json_blob: Dict[str, Any]):
        """Constructs an LFMTrackInfo instance from the LFM API's track.getinfo endpoint JSON response."""
        release_json = json_blob["album"]
        release_mbid = None if "mbid" not in release_json else release_json["mbid"]
        return cls(
            artist=json_blob["artist"]["name"],
            track_name=json_blob["name"],
            release_mbid=release_mbid,
            release_name=release_json["title"],
            lfm_url=json_blob["url"],
        )

    def get_release_mbid(self) -> Optional[str]:
        return self.release_mbid
