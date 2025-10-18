# from abc import ABC, abstractmethod
from datetime import datetime
from urllib.parse import quote_plus

from pydantic import BaseModel, ConfigDict, Field

from plastered.models.types import EntityType, RecContext

# TODO (later): subclass LFMRec and ManualSearch to this class.
# class InitialSearchInfo(BaseModel, ABC):
#     """
#     Abstract base class for representing an input search's details. Subclassed by LFM searches and manual searches.
#     """
#     model_config = ConfigDict(extra="forbid")
# entity_type: EntityType
# artist: str
# entity: str
# mbid: str | None = None

#     @property
#     @abstractmethod
#     def lfm_entity_url(self) -> str:
#         """Returns the LFM URL to the entity. Existence of URL is not validated during construction."""
#         pass

#     @property
#     @abstractmethod
#     def encoded_artist_str(self) -> str:
#         """Returns the URL-encoded (via quote_plus) string of the artist."""
#         pass

#     @property
#     @abstractmethod
#     def encoded_entity_str(self) -> str:
#         """Returns the URL-encoded (via quote_plus) string of the entity."""
#         pass

#     @property
#     @abstractmethod
#     def rec_context(self) -> RecContext:
#         """Returns the LFM context from which the search originated. for non-LFM searches, set to `NOT_SET`."""
#         pass

#     @abstractmethod
#     def get_human_readable_track_str(self) -> str:
#         """Returns the non-URL encoded track name if the instance relates to a Track, otherwise raises an exception."""
#         pass

#     def get_human_readable_artist_str(self) -> str:
#         return self.artist

#     def get_human_readable_entity_str(self) -> str:
#         return self.entity


def _default_submit_timestamp_factory() -> int:
    return int(datetime.now().timestamp())


class ManualSearch(BaseModel):
    """Model for the manual search payload passed to the ReleaseSearcher by the API manual search form."""

    model_config = ConfigDict(extra="forbid")
    entity_type: EntityType
    artist: str
    entity: str
    mbid: str | None = None
    submit_timestamp: int = Field(default_factory=_default_submit_timestamp_factory)

    @property
    def lfm_entity_url(self) -> str:
        if self.entity_type == EntityType.ALBUM:
            return f"https://www.last.fm/music/{self.encoded_artist_str}/{self.encoded_entity_str}"
        return f"https://www.last.fm/music/{self.encoded_artist_str}/_/{self.encoded_entity_str}"

    @property
    def encoded_artist_str(self) -> str:
        return quote_plus(self.artist)

    @property
    def encoded_entity_str(self) -> str:
        return quote_plus(self.entity)

    @property
    def rec_context(self) -> RecContext:
        return RecContext.NOT_SET

    def get_human_readable_entity_str(self) -> str:
        return self.entity

    def get_human_readable_artist_str(self) -> str:
        return self.artist

    def get_human_readable_track_str(self) -> str:
        if not self.entity_type == EntityType.TRACK:
            raise ValueError("Cannot get track name from Album entity.")
        return self.entity
