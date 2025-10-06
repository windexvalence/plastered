from pydantic import BaseModel, ConfigDict

from plastered.models.types import EntityType


class ManualSearch(BaseModel):
    """Model for the manual search payload passed to the ReleaseSearcher by the API manual search form."""
    model_config = ConfigDict(extra="ignore")
    entity_type: EntityType
    artist: str
    entity: str
    mbid: str | None = None

    def get_human_readable_release_str(self) -> str:
        return self.entity
    
    def get_human_readable_artist_str(self) -> str:
        return self.artist

    def get_human_readable_track_str(self) -> str:
        if not self.entity_type == EntityType.TRACK:
            raise ValueError("Cannot get track name from Album entity.")
        return self.entity
