import re
from typing import Final, Generator
from unittest.mock import MagicMock, patch, PropertyMock

from fastapi import HTTPException
import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from plastered.actions.api_actions import inspect_run_action, run_history_action, manual_search_action
from plastered.config.app_settings import AppSettings
from plastered.db.db_models import FinalState, SearchResult, SearchRun
from plastered.models.manual_search_models import ManualSearch
from plastered.models.red_models import TorrentEntry
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
def empty_search_run_table(mock_session: Session) -> Generator[Session, None, None]:
    """Yields a `Session` instance pointing to an empty `SearchRun` table."""
    yield mock_session


@pytest.fixture(scope="function")
def mock_search_run_instance() -> SearchRun:
    """Returns a mock `SearchRun` instance, used by the `non_empty_search_run_table` fixture."""
    return SearchRun(
        id=_MOCK_RECORD_ID,
        submit_timestamp=_MOCK_SINCE_TIMESTAMP + 1,
        is_manual=True,
        entity_type=EntityType.ALBUM,
        artist="Fake Artist",
        entity="Fake Album",
    )


@pytest.fixture(scope="function")
def non_empty_search_run_table(
    mock_session: Session, mock_search_run_instance: SearchRun
) -> Generator[Session, None, None]:
    """Yields a `Session` instance pointing to a non-empty `SearchRun` table."""
    mock_session.add(mock_search_run_instance)
    mock_session.commit()
    mock_session.refresh(mock_search_run_instance)
    yield mock_session


def test_run_history_action_empty_table(empty_search_run_table: Session) -> None:
    """Tests the `run_history_action` returns an empty list when no records are within the since_timestamp."""
    mock_since = _MOCK_SINCE_TIMESTAMP
    actual = run_history_action(since_timestamp=mock_since, session=empty_search_run_table)
    assert isinstance(actual, list)
    assert len(actual) == 0


def test_run_history_action_non_empty_table(
    non_empty_search_run_table: Session, mock_search_run_instance: SearchRun
) -> None:
    """Tests the `run_history_action` returns a non-empty list when records are within the since_timestamp."""
    mock_since = _MOCK_SINCE_TIMESTAMP
    actual = run_history_action(since_timestamp=mock_since, session=non_empty_search_run_table)
    assert isinstance(actual, list)
    assert len(actual) == 1
    assert actual[0] is mock_search_run_instance


@pytest.fixture(scope="function")
def mock_search_run() -> SearchRun:
    return SearchRun(
        is_manual=True, artist="a", entity="b", submit_timestamp=_MOCK_SINCE_TIMESTAMP, entity_type=EntityType.ALBUM
    )


@pytest.fixture(scope="function")
def mock_te() -> MagicMock:
    mt = MagicMock(spec=TorrentEntry)
    type(mt).torrent_id = PropertyMock(return_value=123)
    return mt


@pytest.mark.asyncio
async def test_manual_search_action(
    valid_app_settings: AppSettings, mock_session: Session, mock_search_run: SearchRun, mock_te: MagicMock
) -> None:
    mock_si = SearchItem(
        initial_info=ManualSearch(entity_type=EntityType.ALBUM, artist="a", entity="b"),
        torrent_entry=mock_te,
        search_result=SearchResult(final_state=FinalState.SUCCESS),
    )
    with (
        patch.object(ReleaseSearcher, "manual_search"),
        patch.object(ReleaseSearcher, "get_finalized_manual_search_item", return_value=mock_si),
    ):
        actual = await manual_search_action(
            session=mock_session, app_settings=valid_app_settings, search_run=mock_search_run
        )
        search_run_records = mock_session.exec(select(SearchRun)).all()
        assert len(search_run_records) == 1
        search_result_records = mock_session.exec(select(SearchResult)).all()
        assert len(search_result_records) == 1
        assert search_result_records[0].search_run_id == actual["search_run_id"]


@pytest.mark.asyncio
async def test_manual_search_action_state_failed(
    valid_app_settings: AppSettings, mock_session: Session, mock_search_run: SearchRun, mock_te: MagicMock
) -> None:
    with (
        patch.object(ReleaseSearcher, "manual_search"),
        patch.object(ReleaseSearcher, "get_finalized_manual_search_item", return_value=None),
        pytest.raises(HTTPException, match=re.escape("SearchItem not found")),
    ):
        _ = await manual_search_action(
            session=mock_session, app_settings=valid_app_settings, search_run=mock_search_run
        )
    search_item_records = mock_session.exec(select(SearchRun)).all()
    assert len(search_item_records) == 1
    search_result_records = mock_session.exec(select(SearchResult)).all()
    assert len(search_result_records) == 0


def test_inspect_run_action_empty_table(empty_search_run_table: Session) -> None:
    """Ensures `inspect_run_action` returns `None` when no records match the provided `run_id`."""
    actual = inspect_run_action(run_id=_MOCK_RECORD_ID, session=empty_search_run_table)
    assert actual is None


def test_inspect_run_action_match(non_empty_search_run_table: Session, mock_search_run_instance: SearchRun) -> None:
    """Ensures `inspect_run_action` returns a `SearchRun` instance for the existing record when there's a match."""
    actual = inspect_run_action(run_id=_MOCK_RECORD_ID, session=non_empty_search_run_table)
    assert isinstance(actual, SearchRun)
    assert actual is mock_search_run_instance
