from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote_plus

from plastered.models.types import EntityType
from plastered.utils.exceptions import LFMRecException


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


class LFMRec:
    """
    Class representing a singular recommendation from LFM.
    Corresponds to either a distinct LFM Album recommendation, or a distinct LFM Track recommendation.
    """

    def __init__(self, lfm_artist_str: str, lfm_entity_str: str, recommendation_type: str | EntityType):
        self._lfm_artist_str = lfm_artist_str
        self._lfm_entity_str = lfm_entity_str
        self._entity_type = EntityType(recommendation_type)

    def __str__(self) -> str:
        return f"artist={self._lfm_artist_str}, {self._entity_type.value}={self._lfm_entity_str}"

    def __eq__(self, other) -> bool:
        if not isinstance(other, LFMRec):
            return False
        return (
            self.encoded_artist_str == other.encoded_artist_str
            and self.encoded_entity_str == other.encoded_entity_str
            and self.is_album_rec() == other.is_album_rec()
        )

    def is_album_rec(self) -> bool:
        return self._entity_type == EntityType.ALBUM

    def is_track_rec(self) -> bool:
        return self._entity_type == EntityType.TRACK

    @property
    def encoded_artist_str(self) -> str:
        return self._lfm_artist_str

    def get_human_readable_artist_str(self) -> str:
        return unquote_plus(self._lfm_artist_str)

    def get_human_readable_entity_str(self) -> str:
        return unquote_plus(self._lfm_entity_str)

    def get_human_readable_track_str(self) -> str:
        if not self.is_track_rec():
            raise LFMRecException(
                f"Cannot get the track name from an LFMRec instance with a {self._entity_type.value} reccommendation type."
            )
        return unquote_plus(self._lfm_entity_str)

    @property
    def encoded_entity_str(self) -> str:
        return self._lfm_entity_str

    @property
    def entity_type(self) -> EntityType:
        return self._entity_type

    @property
    def lfm_entity_url(self) -> str:
        if self._entity_type == EntityType.ALBUM:
            return f"https://www.last.fm/music/{self._lfm_artist_str}/{self._lfm_entity_str}"
        return f"https://www.last.fm/music/{self._lfm_artist_str}/_/{self._lfm_entity_str}"
