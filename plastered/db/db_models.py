"""
Collection of db models that are compatible with FastAPI, per the docs at the links below:
https://fastapi.tiangolo.com/tutorial/sql-databases/#create-models
https://sqlmodel.tiangolo.com/
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Final

from sqlmodel import Field, SQLModel, create_engine

from plastered.config.app_settings import get_app_settings
from plastered.models.types import EncodingEnum, EntityType, FormatEnum, MediaEnum

if TYPE_CHECKING:
    from sqlalchemy.engine.base import Engine


class Status(StrEnum):
    FAILED = "failed"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    SKIPPED = "skipped"


class SkipReason(StrEnum):
    ABOVE_MAX_ALLOWED_SIZE = "Above max allowed size"
    NO_MATCH_FOUND = "No RED match found"
    ALREADY_SNATCHED = "Already snatched from release group"
    DUPE_OF_ANOTHER_REC = "Dupe of other release pending download"
    REC_CONTEXT_FILTERING = "LFM Recs with context 'in-library' ignored when 'allow_library_items' = false"
    NO_SOURCE_RELEASE_FOUND = "Could not associate track rec with a release"
    MIN_RATIO_LIMIT = "Snatch would drop ratio below configured 'min_allowed_ratio'"
    UNRESOLVED_REQUIRED_SEARCH_FIELDS = (
        "Could not resolve 1 or more of: first_release_year record_label, catalog_number"
    )


class FailReason(StrEnum):
    RED_API_REQUEST_ERROR = "RedClientSnatchException"
    FILE_ERROR = OSError.__name__
    OTHER = "Exception - other"


class Result(SQLModel, table=True):
    """
    Model for the result table, which contains a record per COMPLETED manual search or scraper search run.
    May contain both failed, skipped, or successful snatch results for each given search.
    Has a foreign key relation to the `SearchRun` records, which correspond to all searches,
    including active ones (i.e. searches not present in this table).

    https://sqlmodel.tiangolo.com/tutorial/connect/create-connected-tables/?h=foreign#create-the-team-table
    """

    id: int | None = Field(default=None, primary_key=True)
    submit_timestamp: int
    is_manual: bool
    entity_type: EntityType
    artist: str
    entity: str
    media: MediaEnum | None = Field(default=None)
    encoding: EncodingEnum | None = Field(default=None)
    format: FormatEnum | None = Field(default=None)
    status: Status | None = Field(default=None)


class Skipped(SQLModel, table=True):
    """
    Model for the `skipped` table, populated by the SearchState during a scraper run or manual search.
    Each record corresponds to a given entity which was skipped, along with the metadata related to that skip.
    """

    id: int | None = Field(default=None, primary_key=True)
    s_result_id: int | None = Field(default=None, foreign_key="result.id")
    skip_reason: SkipReason


class Failed(SQLModel, table=True):
    """
    Model for the `failed` table, populated by the SearchState during a scraper run or manual search.
    Each record corresponds to a given entity where searching failed, along with the metadata related to that failure.
    """

    id: int | None = Field(default=None, primary_key=True)
    f_result_id: int | None = Field(default=None, foreign_key="result.id")
    red_permalink: str | None = Field(default=None)
    matched_mbid: str | None = Field(default=None)
    fail_reason: FailReason


class Grabbed(SQLModel, table=True):
    """
    Model for the `grabbed` table, populated by the SearchState during a scraper run or manual search.
    Each record corresponds to a given entity which was successfully snatched from RED, along with the
    metadata related to the snatch.
    """

    id: int | None = Field(default=None, primary_key=True)
    g_result_id: int | None = Field(default=None, foreign_key="result.id")
    fl_token_used: bool | None = Field(default=None)
    snatch_path: str | None = Field(default=None)
    tid: int | None = Field(default=None)


_DB_FILEPATH: Final[str] = get_app_settings().get_db_filepath()
_SQLITE_URL: Final[str] = f"sqlite:///{_DB_FILEPATH}"
ENGINE: Final[Engine] = create_engine(_SQLITE_URL, connect_args={"check_same_thread": False})
