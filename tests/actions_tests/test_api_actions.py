from typing import Generator
from unittest.mock import MagicMock

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from plastered.actions.api_actions import run_history_action, manual_search_action
from plastered.config.app_settings import AppSettings
from plastered.db.db_models import SearchRun
from plastered.models.types import EntityType


@pytest.fixture(scope="session")
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


@pytest.mark.asyncio
async def test_manual_search_action(valid_app_settings: AppSettings, mock_session: Session) -> None:
    mock_search_run = SearchRun(
        is_manual=True,
        artist="fake artist",
        entity="fake album",
        submit_timestamp=1759680000,
        entity_type=EntityType.ALBUM,
    )
    actual = await manual_search_action(session=mock_session, app_settings=valid_app_settings, search_run=mock_search_run)
    assert actual is not None
