from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from plastered.db.db_models import Failed, Grabbed, SearchRecord, Skipped

if TYPE_CHECKING:
    from sqlalchemy import Row


class RunHistoryListResponse(BaseModel):
    """FastAPI response model for the non-HTMX response from the `/api/run_history` endpoint."""

    runs: list[RunHistoryItem]
    since_timestamp: int
    submitted_search_id: int = Field(default=-1)


class RunHistoryItem(BaseModel):
    # TODO: rename this field to `search_record`
    searchrecord: SearchRecord
    failed: Failed | None = Field(default=None)
    grabbed: Grabbed | None = Field(default=None)
    skipped: Skipped | None = Field(default=None)

    @classmethod
    def from_sql_row(cls, row: Row) -> RunHistoryItem:
        return cls(**{k.lower(): v for k, v in row._asdict().items()})
