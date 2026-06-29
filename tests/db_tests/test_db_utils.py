from typing import Any
from unittest.mock import ANY, MagicMock, patch

import pytest
from sqlmodel import Field, Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from plastered.db.db_models import FailReason, SearchProgress, SearchRecord, SkipReason, Status
from plastered.db.db_utils import add_record, get_result_by_id, set_result_status, upsert_search_progress
from plastered.utils.exceptions import MissingDatabaseRecordException


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


def test_add_record_no_session() -> None:
    m1 = MockTable(foo="a", bar="b")
    with (
        patch("plastered.db.db_utils.get_engine") as mock_get_engine,
        patch("plastered.db.db_utils._add_record") as mock_internal_add_record_fn,
    ):
        _ = add_record(model_inst=m1)
        mock_get_engine.assert_called_once()
        mock_internal_add_record_fn.assert_called_once_with(session=ANY, model_inst=m1)


@pytest.mark.parametrize(
    "mock_status, mock_status_model_kwargs",
    [
        (Status.FAILED, {"red_permalink": None, "matched_mbid": None, "fail_reason": FailReason.OTHER}),
        (Status.GRABBED, {"fl_token_used": None, "snatch_path": None, "tid": None}),
        (Status.SKIPPED, {"skip_reason": SkipReason.NO_SOURCE_RELEASE_FOUND}),
        (Status.MATCHED, {"tid": 420, "red_permalink": "https://red/x", "size_gb": 1.0}),
    ],
)
def test_set_result_status(
    mock_album_result: SearchRecord, mock_status: Status, mock_status_model_kwargs: dict[str, Any]
) -> None:
    fake_id = 69
    mock_sesh = MagicMock()
    with (
        patch.object(Session, "__enter__", return_value=mock_sesh),
        patch("plastered.db.db_utils.get_result_by_id", return_value=mock_album_result) as mock_get_result_by_id,
    ):
        _ = set_result_status(search_id=fake_id, status=mock_status, status_model_kwargs=mock_status_model_kwargs)
        mock_get_result_by_id.assert_called_once_with(search_id=fake_id, session=mock_sesh)
        assert len(mock_sesh.add.mock_calls) == 2
        mock_sesh.commit.assert_called_once()


def test_set_result_status_fails() -> None:
    with pytest.raises(MissingDatabaseRecordException):
        set_result_status(search_id=None, status=Status.FAILED, status_model_kwargs={})


@pytest.mark.parametrize(
    "search_id, session, should_fail",
    [
        (None, None, True),
        (None, MagicMock(spec=Session), True),
        (69, MagicMock(spec=Session), False),
        (69, None, False),
    ],
)
def test_get_result_by_id(
    mock_album_result: SearchRecord, search_id: int | None, session: Session | None, should_fail: bool
) -> None:
    with (
        patch.object(Session, "__enter__") as mock_sesh_ctx,
        patch("plastered.db.db_utils._get_rows", return_value=[mock_album_result]),
    ):
        if should_fail:
            with pytest.raises(MissingDatabaseRecordException):
                _ = get_result_by_id(search_id=search_id, session=session)
        else:
            _ = get_result_by_id(search_id=search_id, session=session)
            if session:
                mock_sesh_ctx.assert_not_called()
            else:
                mock_sesh_ctx.assert_called_once()


def test_upsert_search_progress_inserts_then_updates() -> None:
    """`upsert_search_progress` keeps a single progress row per search id, updating it as the search advances."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with patch("plastered.db.db_utils.get_engine", return_value=engine):
        upsert_search_progress(search_id=69, current_pref=1, total_prefs=3, current_pref_label="FLAC / Lossless / CD")
        upsert_search_progress(
            search_id=69, current_pref=2, total_prefs=3, current_pref_label="FLAC / 24bit Lossless / SACD"
        )
    with Session(engine) as session:
        rows = list(session.exec(select(SearchProgress).where(SearchProgress.sp_result_id == 69)).all())
    assert len(rows) == 1
    assert rows[0].current_pref == 2
    assert rows[0].total_prefs == 3
    assert "SACD" in rows[0].current_pref_label
