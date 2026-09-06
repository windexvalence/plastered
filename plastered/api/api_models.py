from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from plastered.config.app_settings import RedSearchOverrides
from plastered.db.db_models import (
    Failed,
    Grabbed,
    Matched,
    RecDownloadBatch,
    ScrapeCadence,
    ScraperRun,
    ScrapeSchedule,
    SearchRecord,
    SearchStep,
    Skipped,
    SkipReason,
    Status,
)
from plastered.models import AdhocSearch, EntityType, SearchStepOutcome

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
    download was requested and succeeded) and any snatch information. `steps` is the search trace so far, in chain
    order (see `plastered.models.search_trace`): what each stage found and, for a search that found no release, where
    it stopped.
    """

    searchrecord: SearchRecord
    matched: Matched | None = Field(default=None)
    grabbed: Grabbed | None = Field(default=None)
    failed: Failed | None = Field(default=None)
    skipped: Skipped | None = Field(default=None)
    steps: list[SearchStep] = Field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """`True` once the search has reached a terminal status (i.e. is no longer in progress)."""
        return self.searchrecord.status is not None and self.searchrecord.status != Status.IN_PROGRESS

    @property
    def stopped_step(self) -> SearchStep | None:
        """The trace step at which a filter dropped the search, if any."""
        return next((step for step in reversed(self.steps) if step.outcome == SearchStepOutcome.STOPPED), None)


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
    matched: Matched | None = Field(default=None)

    @classmethod
    def from_sql_row(cls, row: Row) -> RunHistoryItem:
        return cls(**{k.lower(): v for k, v in row._asdict().items()})

    @property
    def is_retryable(self) -> bool:
        """`True` for an ad-hoc search that found no RED match, which the run-history page offers to re-submit."""
        return (
            self.searchrecord.is_manual
            and self.skipped is not None
            and self.skipped.skip_reason == SkipReason.NO_MATCH_FOUND
        )


class RunHistoryRow(BaseModel):
    """
    A single run-history row, discriminated by `kind`: an `adhoc` ad-hoc search (one rec) or a `scraper` LFM scraper
    run (which carries the recs it pulled in `scraper_recs`).
    """

    kind: str  # "adhoc" | "scraper"
    sort_timestamp: int
    adhoc: RunHistoryItem | None = Field(default=None)
    scraper: ScraperRun | None = Field(default=None)
    scraper_recs: list[RunHistoryItem] | None = Field(default=None)
    download_batch: RecDownloadBatch | None = Field(default=None)


class RunHistoryPageResponse(BaseModel):
    """A single page of run-history results for the HTML accordion view, newest-first by default."""

    rows: list[RunHistoryRow]
    page: int
    page_size: int
    total_count: int
    total_pages: int
    status_filter: Status | None = Field(default=None)
    query: str | None = Field(default=None)
    sort_desc: bool = Field(default=True)
    search_id: int | None = Field(default=None)


class ScrapeScheduleRequest(BaseModel):
    """
    Request body for configuring the (single) scheduled LFM scraper run. The scrape first runs at the next occurrence
    of `hour:minute` (server-local time) and then repeats per `cadence`.
    """

    model_config = ConfigDict(extra="forbid")
    cadence: ScrapeCadence
    hour: int = Field(default=3, ge=0, le=23, description="Hour of the day (server-local time) the scrape runs at.")
    minute: int = Field(default=0, ge=0, le=59)
    rec_type: EntityType | None = Field(
        default=None, description="Scrape only this rec type; `null` scrapes every type in `lfm.rec_types_to_scrape`."
    )
    snatch: bool = Field(default=False, description="Download the top RED match of each recommendation.")


class ScrapeScheduleResponse(BaseModel):
    """The configured scheduled scrape, with its next run time and the most recent scraper run it started (if any)."""

    schedule: ScrapeSchedule
    next_run_timestamp: int | None = Field(default=None)
    last_run: ScraperRun | None = Field(default=None)


class LoginRequestBody(BaseModel):
    username: SecretStr
    password: SecretStr


class LoginResponseBody(BaseModel):
    """The raw bearer token the client must send back as `Authorization: Bearer <token>` (`str`, not
    `SecretStr` — this response is the one place the token is intentionally revealed)."""

    token: str
    token_type: Literal["bearer"] = "bearer"


class LogoutResponseBody(BaseModel):
    detail: str = "Logged out."
