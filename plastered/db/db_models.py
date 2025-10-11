"""
Collection of db models that are compatible with FastAPI, per the docs at the link below:
https://fastapi.tiangolo.com/tutorial/sql-databases/#create-models
"""

from enum import StrEnum

from sqlmodel import Field, SQLModel

from plastered.models.types import EntityType


class RunState(StrEnum):
    ACTIVE = "active"
    SUCCESS = "success"
    SKIPPED = "skipped"  # TODO (later): Have a way for SearchItem to maintain whether self was skipped
    FAILED = "failed"


class SearchRun(SQLModel, table=True):
    """Model for the search_run table, which contains a record per manual search or scraper search run submission."""

    id: int | None = Field(default=None, primary_key=True)
    submit_timestamp: int
    is_manual: bool
    entity_type: EntityType
    artist: str
    entity: str
    state: RunState | None = Field(default=RunState.ACTIVE)
    tid: int | None = Field(default=None)
