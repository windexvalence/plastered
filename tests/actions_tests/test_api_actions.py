import re
from typing import Final, Generator
from unittest.mock import MagicMock, patch, PropertyMock

from fastapi import HTTPException
import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from plastered.actions.api_actions import (
    adhoc_result_action,
    adhoc_search_action,
    inspect_run_action,
    run_history_action,
)
from plastered.api.api_models import AdhocSearchResult, RunHistoryListResponse
from plastered.config.app_settings import AppSettings
from plastered.db.db_models import Matched, SearchRecord, Status
from plastered.models.adhoc_search_models import AdhocSearch
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


def test_adhoc_search_action() -> None:
    """Ensures `adhoc_search_action` delegates to the shared `ReleaseSearcher` and returns the resulting record."""
    mock_search_id = 69
    mock_adhoc_search = AdhocSearch(artist="Fake Artist", release="Fake Album")
    mock_release_searcher = MagicMock(spec=ReleaseSearcher)
    with patch(
        "plastered.actions.api_actions.get_result_by_id", return_value=MagicMock(spec=SearchRecord)
    ) as mock_get_res:
        _ = adhoc_search_action(
            release_searcher=mock_release_searcher, adhoc_search=mock_adhoc_search, search_id=mock_search_id
        )
        mock_release_searcher.adhoc_search.assert_called_once_with(
            adhoc_search=mock_adhoc_search, search_id=mock_search_id, overrides=None
        )
        mock_get_res.assert_called_once_with(search_id=mock_search_id)


def test_adhoc_result_action_no_record(empty_tables: Session) -> None:
    """Ensures `adhoc_result_action` returns `None` when there is no record for the given search id."""
    assert adhoc_result_action(search_id=_MOCK_RECORD_ID, session=empty_tables) is None


def test_adhoc_result_action_with_match(mock_session: Session) -> None:
    """Ensures `adhoc_result_action` surfaces the search record plus the produced status rows."""
    record = SearchRecord(
        id=_MOCK_RECORD_ID,
        submit_timestamp=_MOCK_SINCE_TIMESTAMP,
        is_manual=True,
        entity_type=EntityType.ALBUM,
        artist="Fake Artist",
        entity="Fake Album",
        status=Status.MATCHED,
    )
    matched = Matched(m_result_id=_MOCK_RECORD_ID, tid=_MOCK_RECORD_TID, red_permalink="https://red/x", size_gb=1.0)
    mock_session.add(record)
    mock_session.add(matched)
    mock_session.commit()
    actual = adhoc_result_action(search_id=_MOCK_RECORD_ID, session=mock_session)
    assert isinstance(actual, AdhocSearchResult)
    assert actual.is_complete is True
    assert actual.matched is not None and actual.matched.tid == _MOCK_RECORD_TID
    assert actual.grabbed is None and actual.failed is None and actual.skipped is None


def test_inspect_run_action_empty_table(empty_tables: Session) -> None:
    """Ensures `inspect_run_action` returns `None` when no records match the provided `run_id`."""
    actual = inspect_run_action(run_id=_MOCK_RECORD_ID, session=empty_tables)
    assert actual is None


def test_inspect_run_action_match(non_empty_tables: Session, mock_search_result_instance: SearchRecord) -> None:
    """Ensures `inspect_run_action` returns a `SearchRun` instance for the existing record when there's a match."""
    actual = inspect_run_action(run_id=_MOCK_RECORD_ID, session=non_empty_tables)
    assert isinstance(actual, SearchRecord)
    assert actual is mock_search_result_instance
