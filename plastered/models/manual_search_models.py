from urllib.parse import quote_plus

from pydantic import BaseModel, ConfigDict

from plastered.models.types import EntityType, RecContext


class ManualSearch(BaseModel):
    """Model for the manual search payload passed to the ReleaseSearcher by the API manual search form."""

    model_config = ConfigDict(extra="ignore")
    entity_type: EntityType
    artist: str
    entity: str
    mbid: str | None = None

    @property
    def lfm_entity_url(self) -> str:
        if self.entity_type == EntityType.TRACK:
            return f"https://www.last.fm/music/{self.encoded_artist_str}/_/{self.encoded_entity_str}"
        return f"https://www.last.fm/music/{self.encoded_artist_str}/{self.encoded_entity_str}"

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

    def get_human_readable_release_str(self) -> str:
        return self.entity

    def get_human_readable_artist_str(self) -> str:
        return self.artist

    def get_human_readable_track_str(self) -> str:
        if not self.entity_type == EntityType.TRACK:
            raise ValueError("Cannot get track name from Album entity.")
        return self.entity
