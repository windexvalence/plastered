from typing import Generator
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from plastered.actions.api_actions import run_history_action, manual_search_action
from plastered.config.app_settings import AppSettings
from plastered.db.db_models import SearchRun
from plastered.models.manual_search_models import ManualSearch
from plastered.models.red_models import TorrentEntry
from plastered.models.search_item import SearchItem
from plastered.models.types import EntityType
from plastered.release_search.release_searcher import ReleaseSearcher


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


def test_run_history_action(mock_session: Session) -> None:
    mock_since = 1759680000
    _ = run_history_action(since_timestamp=mock_since, session=mock_session)


@pytest.fixture(scope="function")
def mock_search_run() -> SearchRun:
    return SearchRun(is_manual=True, artist="a", entity="b", submit_timestamp=1759680000, entity_type=EntityType.ALBUM)


@pytest.fixture(scope="function")
def mock_te() -> MagicMock:
    mt = MagicMock(spec=TorrentEntry)
    type(mt).torrent_id = PropertyMock(return_value=123)
    return mt


@pytest.mark.asyncio
async def test_manual_search_action(
    valid_app_settings: AppSettings, mock_session: Session, mock_search_run: SearchRun, mock_te: MagicMock
) -> None:
    with (
        patch.object(ReleaseSearcher, "manual_search"),
        patch.object(
            ReleaseSearcher,
            "get_snatched_manual_search_item",
            return_value=SearchItem(
                initial_info=ManualSearch(entity_type=EntityType.ALBUM, artist="a", entity="b"), torrent_entry=mock_te
            ),
        ),
    ):
        actual = await manual_search_action(
            session=mock_session, app_settings=valid_app_settings, search_run=mock_search_run
        )
        assert actual is not None
        search_item_records = mock_session.exec(select(SearchRun)).all()
        assert len(search_item_records) == 1
        assert search_item_records[0].model_dump() == actual


@pytest.mark.asyncio
async def test_manual_search_action_state_failed(
    valid_app_settings: AppSettings, mock_session: Session, mock_search_run: SearchRun, mock_te: MagicMock
) -> None:
    with (
        patch.object(ReleaseSearcher, "manual_search"),
        patch.object(ReleaseSearcher, "get_snatched_manual_search_item", return_value=None),
    ):
        actual = await manual_search_action(
            session=mock_session, app_settings=valid_app_settings, search_run=mock_search_run
        )
        assert actual is not None
        search_item_records = mock_session.exec(select(SearchRun)).all()
        assert len(search_item_records) == 1
        assert search_item_records[0].model_dump() == actual
        assert actual["state"] == "failed"
