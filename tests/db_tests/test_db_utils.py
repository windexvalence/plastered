from typing import Any
from unittest.mock import ANY, MagicMock, patch

import pytest
from sqlmodel import Field, Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from sqlalchemy.exc import OperationalError

from plastered.db.db_models import FailReason, ScrapeCadence, ScrapeSchedule, SearchRecord, SkipReason, Status
from plastered.db.db_utils import (
    _CREATE_TABLES_MAX_ATTEMPTS,
    add_record,
    db_startup,
    delete_scrape_schedule,
    get_result_by_id,
    get_scrape_schedule,
    set_result_status,
    update_scrape_schedule,
    upsert_scrape_schedule,
)
from plastered.models.types import EntityType
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


def test_create_and_update_and_get_scraper_run() -> None:
    """create_scraper_run inserts an IN_PROGRESS run; update_scraper_run mutates fields by id."""
    from plastered.db.db_models import ScraperRun, ScraperRunStatus
    from plastered.db.db_utils import create_scraper_run, update_scraper_run

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with patch("plastered.db.db_utils.get_engine", return_value=engine):
        run_id = create_scraper_run(snatch_enabled=True, rec_types=["album", "track"], submit_timestamp=1759680000)
        update_scraper_run(run_id=run_id, stage="searching", progress_current=2, progress_total=5)
        update_scraper_run(run_id=run_id, status=ScraperRunStatus.COMPLETED, total_recs=5)
    with Session(engine) as session:
        run = session.exec(select(ScraperRun).where(ScraperRun.id == run_id)).one()
    assert run.snatch_enabled is True
    assert run.rec_types == "album,track"
    assert run.stage == "searching" and run.progress_current == 2 and run.progress_total == 5
    assert run.status == ScraperRunStatus.COMPLETED and run.total_recs == 5
    engine.dispose()


def test_rec_download_batch_lifecycle() -> None:
    """create_rec_download_batch inserts IN_PROGRESS; increment/complete advance it."""
    from plastered.db.db_models import RecDownloadBatch, RecDownloadBatchStatus
    from plastered.db.db_utils import (
        complete_rec_download_batch,
        create_rec_download_batch,
        increment_rec_download_batch,
    )

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with patch("plastered.db.db_utils.get_engine", return_value=engine):
        batch_id = create_rec_download_batch(scraper_run_id=7, total=3, submit_timestamp=1759680000)
        increment_rec_download_batch(batch_id=batch_id)
        increment_rec_download_batch(batch_id=batch_id)
        with Session(engine) as session:
            mid = session.exec(select(RecDownloadBatch).where(RecDownloadBatch.id == batch_id)).one()
        assert mid.status == RecDownloadBatchStatus.IN_PROGRESS and mid.completed == 2 and mid.total == 3
        complete_rec_download_batch(batch_id=batch_id)
    with Session(engine) as session:
        final = session.exec(select(RecDownloadBatch).where(RecDownloadBatch.id == batch_id)).one()
    assert final.status == RecDownloadBatchStatus.COMPLETED and final.completed == 2
    engine.dispose()


def _schedule_fields(**overrides) -> dict:
    fields = dict(
        cadence=ScrapeCadence.WEEKLY,
        hour=3,
        minute=30,
        rec_type=None,
        snatch_enabled=False,
        start_timestamp=1759680000,
        created_timestamp=1759670000,
        last_run_id=None,
        last_run_timestamp=None,
    )
    fields.update(overrides)
    return fields


def test_scrape_schedule_lifecycle() -> None:
    """The single schedule row: absent by default, inserted then updated in place by upsert, patched, and deleted."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with patch("plastered.db.db_utils.get_engine", return_value=engine):
        assert get_scrape_schedule() is None
        # Updating/deleting with nothing configured is a no-op.
        update_scrape_schedule(last_run_id=1)
        delete_scrape_schedule()

        created = upsert_scrape_schedule(**_schedule_fields())
        assert created.id is not None and created.cadence == ScrapeCadence.WEEKLY and created.snatch_enabled is False
        with Session(engine) as session:
            assert get_scrape_schedule(session=session) == created

        replaced = upsert_scrape_schedule(
            **_schedule_fields(cadence=ScrapeCadence.MONTHLY, rec_type=EntityType.TRACK, snatch_enabled=True)
        )
        assert replaced.id == created.id  # replaced in place: still a single row
        assert replaced.cadence == ScrapeCadence.MONTHLY and replaced.rec_type == EntityType.TRACK
        assert replaced.snatch_enabled is True

        update_scrape_schedule(last_run_id=7, last_run_timestamp=1759680100)
        current = get_scrape_schedule()
        assert current is not None and (current.last_run_id, current.last_run_timestamp) == (7, 1759680100)
        with Session(engine) as session:
            assert len(session.exec(select(ScrapeSchedule)).all()) == 1

        delete_scrape_schedule()
        assert get_scrape_schedule() is None
    engine.dispose()


def _race_error() -> OperationalError:
    return OperationalError("CREATE TABLE scrapeschedule", {}, Exception("table scrapeschedule already exists"))


def test_db_startup_retries_after_a_concurrent_table_creation() -> None:
    """Losing the CREATE TABLE race yields a benign "already exists" error: creation is re-run and then succeeds."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with (
        patch("plastered.db.db_utils.get_engine", return_value=engine),
        patch.object(SQLModel.metadata, "create_all", side_effect=[_race_error(), None]) as mock_create_all,
    ):
        db_startup()
    assert mock_create_all.call_count == 2
    engine.dispose()


def test_db_startup_gives_up_after_repeated_race_errors() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with (
        patch("plastered.db.db_utils.get_engine", return_value=engine),
        patch.object(SQLModel.metadata, "create_all", side_effect=_race_error()) as mock_create_all,
        pytest.raises(OperationalError, match="already exists"),
    ):
        db_startup()
    assert mock_create_all.call_count == _CREATE_TABLES_MAX_ATTEMPTS
    engine.dispose()


def test_db_startup_reraises_other_operational_errors() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    other_error = OperationalError("CREATE TABLE scrapeschedule", {}, Exception("database is locked"))
    with (
        patch("plastered.db.db_utils.get_engine", return_value=engine),
        patch.object(SQLModel.metadata, "create_all", side_effect=other_error) as mock_create_all,
        pytest.raises(OperationalError, match="database is locked"),
    ):
        db_startup()
    assert mock_create_all.call_count == 1
    engine.dispose()
