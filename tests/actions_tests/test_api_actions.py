import re
from typing import Final, Generator
from unittest.mock import MagicMock, patch, PropertyMock

from fastapi import HTTPException
import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from plastered.actions.api_actions import inspect_run_action, run_history_action, manual_search_action
from plastered.api.api_models import RunHistoryListResponse
from plastered.config.app_settings import AppSettings
from plastered.db.db_models import Status, SearchRecord
from plastered.models.manual_search_models import ManualSearch
from plastered.models.red_models import RedUserDetails, TorrentEntry
from plastered.models.search_item import SearchItem
from plastered.models.types import EntityType
from plastered.release_search.release_searcher import ReleaseSearcher


_MOCK_RECORD_ID: Final[int] = 69
_MOCK_RECORD_TID: Final[int] = 420
_MOCK_SINCE_TIMESTAMP: Final[int] = 1759680000


@pytest.fixture(scope="function")
def mock_session() -> Generator[Session, None, None]:
    """
    Creates a temporary in-memory session, following example here:
    https://sqlmodel.tiangolo.com/tutorial/fastapi/tests/?h=#pytest-fixtures
    """
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(scope="function")
def empty_tables(mock_session: Session) -> Generator[Session, None, None]:
    """Yields a `Session` instance pointing to empty tables."""
    yield mock_session


@pytest.fixture(scope="function")
def mock_search_result_instance() -> SearchRecord:
    """Returns a mock `SearchRun` instance, used by the `non_empty_search_run_table` fixture."""
    return SearchRecord(
        id=_MOCK_RECORD_ID,
        submit_timestamp=_MOCK_SINCE_TIMESTAMP + 1,
        is_manual=True,
        entity_type=EntityType.ALBUM,
        artist="Fake Artist",
        entity="Fake Album",
    )


@pytest.fixture(scope="function")
def non_empty_tables(
    mock_session: Session, mock_search_result_instance: SearchRecord
) -> Generator[Session, None, None]:
    """Yields a `Session` instance pointing to a set of non-empty test tables."""
    mock_session.add(mock_search_result_instance)
    mock_session.commit()
    mock_session.refresh(mock_search_result_instance)
    yield mock_session


@pytest.mark.parametrize(
    "mock_since_timestamp_arg, mock_final_state_arg", [(None, Status.GRABBED), (1, None), (1, Status.SKIPPED)]
)
def test_run_history_action_should_fail(
    empty_tables: Session, mock_since_timestamp_arg: int | None, mock_final_state_arg: Status | None
) -> None:
    """
    Ensures `run_history_action` fails when called with `since_timestamp` and/or `final_state` AND
    `submitted_search_id`.
    """
    with pytest.raises(
        HTTPException,
        match=re.escape("submitted_search_id may not be used in with since_timestamp non-None or final_state non-None"),
    ):
        _ = run_history_action(
            session=empty_tables,
            since_timestamp=mock_since_timestamp_arg,
            final_state=mock_final_state_arg,
            search_id=69,
        )


def test_run_history_action_empty_table(empty_tables: Session) -> None:
    """Tests the `run_history_action` returns an empty list when no records are within the since_timestamp."""
    mock_since = _MOCK_SINCE_TIMESTAMP
    actual = run_history_action(since_timestamp=mock_since, session=empty_tables)
    assert isinstance(actual, RunHistoryListResponse)
    assert len(actual.runs) == 0


def test_run_history_action_non_empty_table(
    non_empty_tables: Session, mock_search_result_instance: SearchRecord
) -> None:
    """Tests the `run_history_action` returns a non-empty list when records are within the since_timestamp."""
    mock_since = _MOCK_SINCE_TIMESTAMP
    actual = run_history_action(since_timestamp=mock_since, session=non_empty_tables)
    assert isinstance(actual, RunHistoryListResponse)
    assert len(actual.runs) == 1
    assert actual.runs[0].searchrecord == mock_search_result_instance


@pytest.fixture(scope="function")
def mock_te() -> MagicMock:
    mt = MagicMock(spec=TorrentEntry)
    type(mt).torrent_id = PropertyMock(return_value=123)
    return mt


@pytest.mark.asyncio
async def test_manual_search_action(
    valid_app_settings: AppSettings, mock_session: Session, mock_te: MagicMock, mock_red_user_details: RedUserDetails
) -> None:
    mock_si = SearchItem(
        initial_info=ManualSearch(entity_type=EntityType.ALBUM, artist="a", entity="b"),
        torrent_entry=mock_te,
        search_id=SearchRecord(state=Status.GRABBED),
    )
    mock_search_id = 69
    with (
        patch.object(ReleaseSearcher, "manual_search") as release_searcher_manual_search,
        patch(
            "plastered.actions.api_actions.get_result_by_id", return_value=MagicMock(spec=SearchRecord)
        ) as mock_get_res,
    ):
        _ = await manual_search_action(
            app_settings=valid_app_settings, red_user_details=mock_red_user_details, search_id=mock_search_id
        )
        release_searcher_manual_search.assert_called_once_with(search_id=mock_search_id, mbid=None)
        mock_get_res.assert_called_once_with(search_id=mock_search_id)


def test_inspect_run_action_empty_table(empty_tables: Session) -> None:
    """Ensures `inspect_run_action` returns `None` when no records match the provided `run_id`."""
    actual = inspect_run_action(run_id=_MOCK_RECORD_ID, session=empty_tables)
    assert actual is None


def test_inspect_run_action_match(non_empty_tables: Session, mock_search_result_instance: SearchRecord) -> None:
    """Ensures `inspect_run_action` returns a `SearchRun` instance for the existing record when there's a match."""
    actual = inspect_run_action(run_id=_MOCK_RECORD_ID, session=non_empty_tables)
    assert isinstance(actual, SearchRecord)
    assert actual is mock_search_result_instance
