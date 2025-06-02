from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from plastered.release_search.search_helpers import SearchItem


@dataclass
class LFMAlbumInfo:
    """
    Utility class wrapping the results of the LFM API's album.getinfo endpoint.
    Used by the ReleaseSearcher when usage of the LFM API is required for resolving certain additional search fields.
    """

    artist: str
    album_name: str
    lfm_url: str
    release_mbid: str | None = None

    @classmethod
    def construct_from_api_response(cls, json_blob: dict[str, Any]):
        """Constructs an LFMAlbumInfo instance from the LFM API's album.getinfo endpoint JSON response."""
        return cls(
            artist=json_blob["artist"],
            release_mbid=json_blob["mbid"],
            album_name=json_blob["name"],
            lfm_url=json_blob["url"],
        )

    def get_release_mbid(self) -> str | None:
        return self.release_mbid


# TODO (later): stop using this class and above class in favor of SearchItem
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
    release_mbid: str | None = None

    @classmethod
    def construct_from_api_response(cls, json_blob: dict[str, Any]):
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

    @classmethod
    def from_mb_origin_release_info(cls, si: "SearchItem", mb_origin_release_info_json: dict[str, Any] | None):
        """
        Constructs an LFMTrackInfo instance from the MB API's 'recording' endpoint response.
        Returns `None` if `mb_origin_release_info_json` is `None`.
        """
        if not mb_origin_release_info_json:
            return None
        return LFMTrackInfo(
            artist=si.artist_name,
            track_name=si.track_name,
            lfm_url=si.lfm_rec.lfm_entity_url,
            release_mbid=mb_origin_release_info_json["origin_release_mbid"],
            release_name=mb_origin_release_info_json["origin_release_name"],
        )

    def get_release_mbid(self) -> str | None:
        return self.release_mbid
