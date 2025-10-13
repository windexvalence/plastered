"""
Collection of db models that are compatible with FastAPI, per the docs at the links below:
https://fastapi.tiangolo.com/tutorial/sql-databases/#create-models
https://sqlmodel.tiangolo.com/
"""

from enum import StrEnum

from sqlmodel import Field, SQLModel

from plastered.models.types import EntityType
from plastered.stats.stats import SkippedReason, SnatchFailureReason


class FinalState(StrEnum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"


class SearchRun(SQLModel, table=True):
    """Model for the search_run table, which contains a record per manual search or scraper search run submission."""

    __tablename__: str = "search_run"  # type: ignore[misc]
    id: int | None = Field(default=None, primary_key=True)
    submit_timestamp: int
    is_manual: bool
    entity_type: EntityType
    artist: str
    entity: str


class SearchResult(SQLModel, table=True):
    """
    Model for the search_result table, which contains a record per COMPLETED manual search or scraper search run.
    May contain both failed, skipped, or successful snatch results for each given search.
    Has a foreign key relation to the `SearchRun` records, which correspond to all searches,
    including active ones (i.e. searches not present in this table).

    https://sqlmodel.tiangolo.com/tutorial/connect/create-connected-tables/?h=foreign#create-the-team-table
    """

    __tablename__: str = "search_result"  # type: ignore[misc]
    id: int | None = Field(default=None, primary_key=True)
    search_run_id: int | None = Field(default=None, foreign_key="search_run.id")
    final_state: FinalState | None = Field(default=None)
    skip_reason: SkippedReason | None = Field(default=None)
    snatch_failure_reason: SnatchFailureReason | None = Field(default=None)
    fl_token_used: bool | None = Field(default=None)
    snatch_path: str | None = Field(default=None)
    tid: int | None = Field(default=None)

    # TODO: figure out which table makes sense to put these fields format attrs in?
    # media: MediaEnum | None = Field(default=None)
