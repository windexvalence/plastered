from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import create_engine, Field, Session, SQLModel, select
from sqlmodel.pool import StaticPool

from plastered.db.db_models import FailReason, Failed, Result, SkipReason, Status
from plastered.db.db_utils import add_record, set_result_status


class MockTable(SQLModel, table=True):
    __tablename__: str = "mock_table"
    id: int | None = Field(default=None, primary_key=True)
    foo: str
    bar: str


def test_add_record(mock_session: Session) -> None:
    m1 = MockTable(foo="a", bar="b")
    assert m1.id is None
    add_record(session=mock_session, model_inst=m1)
    assert isinstance(m1.id, int)
    assert m1.id == 1

    m2 = MockTable(foo="x", bar="y")
    assert m2.id is None
    add_record(session=mock_session, model_inst=m2)
    assert isinstance(m2.id, int)
    assert m2.id == 2

    all_mock_records = mock_session.exec(select(MockTable)).all()
    assert len(all_mock_records) == 2


@pytest.mark.parametrize(
    "mock_status, mock_status_model_kwargs",
    [
        (Status.FAILED, {"red_permalink": None, "matched_mbid": None, "fail_reason": FailReason.OTHER}),
        (Status.GRABBED, {"fl_token_used": None, "snatch_path": None, "tid": None}),
        (Status.SKIPPED, {"skip_reason": SkipReason.NO_SOURCE_RELEASE_FOUND}),
    ],
)
def test_set_result_status(
    mock_album_result: Result, mock_session: Session, mock_status: Status, mock_status_model_kwargs: dict[str, Any]
) -> None:
    with (
        patch.object(mock_session, "refresh") as mock_session_refresh,
        patch.object(mock_session, "add") as mock_session_add,
        patch.object(mock_session, "commit") as mock_session_commit,
    ):
        _ = set_result_status(
            session=mock_session,
            result_record=mock_album_result,
            status=mock_status,
            status_model_kwargs=mock_status_model_kwargs,
        )
        mock_session_refresh.assert_called_once_with(mock_album_result)
        mock_session_commit.assert_called_once()
