from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from plastered.config.app_settings import RedSearchOverrides
from plastered.db.db_models import Failed, Grabbed, Matched, SearchRecord, Skipped, Status
from plastered.models import AdhocSearch

if TYPE_CHECKING:
    from sqlalchemy import Row


class AdhocSearchRequest(BaseModel):
    """
    Request body for the ad-hoc release search REST endpoint. Carries the (non-LFM) search details plus optional
    per-request overrides of the `red.format_preferences` / `red.search` / `red.snatches` config.
    """

    model_config = ConfigDict(extra="forbid")
    search: AdhocSearch
    overrides: RedSearchOverrides | None = Field(default=None)


class AdhocSearchSubmittedResponse(BaseModel):
    """Response returned when an ad-hoc search is accepted. The search runs in the background; poll for the result."""

    search_id: int
    status: Status
    result_url: str


class AdhocSearchResult(BaseModel):
    """
    The full result of an ad-hoc search: the search record plus whichever terminal status row was produced. For a
    completed search this surfaces the matched release(s) (`matched` for a search-only run, or `grabbed` when a
    download was requested and succeeded) and any snatch information.
    """

    searchrecord: SearchRecord
    matched: Matched | None = Field(default=None)
    grabbed: Grabbed | None = Field(default=None)
    failed: Failed | None = Field(default=None)
    skipped: Skipped | None = Field(default=None)

    @property
    def is_complete(self) -> bool:
        """`True` once the search has reached a terminal status (i.e. is no longer in progress)."""
        return self.searchrecord.status is not None and self.searchrecord.status != Status.IN_PROGRESS


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
