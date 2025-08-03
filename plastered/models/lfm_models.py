from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import quote_plus, unquote_plus

from plastered.models.types import RecContext, RecommendationType
from plastered.utils.exceptions import LFMRecException

if TYPE_CHECKING:
    from plastered.models.search_item import SearchItem


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


@dataclass
class LFMTrackInfo:  # TODO (later): stop using this class and above class in favor of SearchItem
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
        release_mbid = release_json.get("mbid", None)
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


class LFMRec:
    """
    Class representing a singular recommendation from LFM.
    Corresponds to either a distinct LFM Album recommendation, or a distinct LFM Track recommendation.
    """

    def __init__(
        self,
        lfm_artist_str: str,
        lfm_entity_str: str,
        recommendation_type: str | RecommendationType,
        rec_context: str | RecContext,
    ):
        self._lfm_artist_str = lfm_artist_str
        self._lfm_entity_str = lfm_entity_str
        self._recommendation_type = RecommendationType(recommendation_type)
        self._rec_context = RecContext(rec_context)
        self._track_origin_release: str | None = None
        self._track_origin_release_mbid: str | None = None

    def __str__(self) -> str:
        return f"artist={self._lfm_artist_str}, {self._recommendation_type.value}={self._lfm_entity_str}, context={self._rec_context.value}"

    def __eq__(self, other) -> bool:
        if not isinstance(other, LFMRec):
            return False
        return (
            self.artist_str == other.artist_str
            and self.entity_str == other.entity_str
            and self.is_album_rec() == other.is_album_rec()
            and self.rec_context.value == other.rec_context.value
        )

    def set_track_origin_release(self, track_origin_release: str) -> None:
        """Set the release that the track rec originated from. Only used for RecommendationType.TRACK instances."""
        if not self.is_track_rec():
            raise LFMRecException(
                f"Cannot set the track_origin_release on a LFMRec instance with a {self._recommendation_type.value} reccommendation type."
            )
        self._track_origin_release = quote_plus(track_origin_release)

    def set_track_origin_release_mbid(self, track_origin_release_mbid: str) -> None:
        """Set the MBID of the release which the track rec originated from. Only used for RecommendationType.TRACK instances."""
        if not self.is_track_rec():
            raise LFMRecException(
                f"Cannot set the track_origin_release_mbid on a LFMRec instance with a {self._recommendation_type.value} reccommendation type."
            )
        self._track_origin_release_mbid = track_origin_release_mbid

    def is_album_rec(self) -> bool:
        return self._recommendation_type == RecommendationType.ALBUM

    def is_track_rec(self) -> bool:
        return self._recommendation_type == RecommendationType.TRACK

    @property
    def artist_str(self) -> str:
        return self._lfm_artist_str

    def get_human_readable_artist_str(self) -> str:
        return unquote_plus(self._lfm_artist_str)

    def get_human_readable_release_str(self) -> str:
        if self.is_track_rec():
            return "None" if not self._track_origin_release else unquote_plus(self._track_origin_release)
        return unquote_plus(self._lfm_entity_str)

    def get_human_readable_entity_str(self) -> str:
        return unquote_plus(self._lfm_entity_str)

    def get_human_readable_track_str(self) -> str:
        if not self.is_track_rec():
            raise LFMRecException(
                f"Cannot get the track name from an LFMRec instance with a {self._recommendation_type.value} reccommendation type."
            )
        return unquote_plus(self._lfm_entity_str)

    def get_human_readable_track_origin_release_str(self) -> str | None:
        if not self.is_track_rec():
            raise LFMRecException(
                f"Cannot get the track_origin_release from an LFMRec instance with a {self._recommendation_type.value} reccommendation type."
            )
        return unquote_plus(self._track_origin_release)

    @property
    def entity_str(self) -> str:
        return self._lfm_entity_str

    @property
    def release_str(self) -> str:
        return (
            self._lfm_entity_str
            if self._recommendation_type == RecommendationType.ALBUM
            else self._track_origin_release
        )

    @property
    def rec_type(self) -> RecommendationType:
        return self._recommendation_type

    @property
    def rec_context(self) -> RecContext:
        return self._rec_context

    @property
    def lfm_entity_url(self) -> str:
        if self._recommendation_type == RecommendationType.ALBUM:
            return f"https://www.last.fm/music/{self._lfm_artist_str}/{self._lfm_entity_str}"
        return f"https://www.last.fm/music/{self._lfm_artist_str}/_/{self._lfm_entity_str}"

    @property
    def track_origin_release_mbid(self) -> str | None:
        if not self.is_track_rec():
            raise LFMRecException(
                f"Cannot get the track_origin_release_mbid from an LFMRec instance with a {self._recommendation_type.value} reccommendation type."
            )
        return self._track_origin_release_mbid
