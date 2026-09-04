from datetime import UTC, datetime
from typing import Generator
from unittest.mock import ANY, patch

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi.testclient import TestClient
import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from plastered.actions.schedule_actions import SCRAPE_SCHEDULE_JOB_ID, restore_scrape_schedule
from plastered.api.app import create_fastapi_app
from plastered.db.db_models import ScrapeCadence, ScrapeSchedule


def test_lifespan_starts_scheduler_and_restores_the_scrape_schedule() -> None:
    """The lifespan puts a running `AsyncIOScheduler` on `app.state`, restores the persisted scrape schedule onto it
    (after the shared searcher the job needs exists), and shuts it down on exit."""
    with patch("plastered.api.app.restore_scrape_schedule") as mock_restore:
        with TestClient(app=create_fastapi_app()) as client:
            scheduler = client.app.state.scheduler
            assert isinstance(scheduler, AsyncIOScheduler)
            assert scheduler.running
            mock_restore.assert_called_once_with(
                scheduler=scheduler, app_settings=ANY, release_searcher=client.app.state.release_searcher
            )
    assert not scheduler.running


@pytest.fixture
def isolated_db_engine() -> Generator[object, None, None]:
    """Routes an app's DB access (lifespan `db_startup`, `SessionDep`, and the `db_utils` helpers) to a private
    in-memory engine so the end-to-end test below leaves no rows behind in the worker's shared test DB."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with (
        patch("plastered.db.db_utils.get_engine", return_value=engine),
        patch("plastered.api.fastapi_dependencies.get_engine", return_value=engine),
    ):
        yield engine
    engine.dispose()


def test_scrape_schedule_end_to_end(isolated_db_engine) -> None:
    """Restores a persisted schedule at startup, then replaces and removes it through the real web + JSON routes,
    checking the DB row and the live scheduler job stay in sync."""
    with Session(isolated_db_engine) as session:
        session.add(
            ScrapeSchedule(
                cadence=ScrapeCadence.WEEKLY,
                hour=1,
                minute=0,
                snatch_enabled=False,
                start_timestamp=int(datetime.now(tz=UTC).timestamp()) + 3600,
                created_timestamp=int(datetime.now(tz=UTC).timestamp()),
            )
        )
        session.commit()

    # Override the session-wide stub so the real restore runs against the pre-seeded row.
    with patch("plastered.api.app.restore_scrape_schedule", restore_scrape_schedule):
        with TestClient(app=create_fastapi_app()) as client:
            scheduler = client.app.state.scheduler
            restored = scheduler.get_job(SCRAPE_SCHEDULE_JOB_ID)
            assert restored is not None and restored.next_run_time is not None
            assert "weekly" in restored.name

            page = client.get("/scrape_schedule")
            assert page.status_code == 200
            assert "A scheduled scrape is configured" in page.text and "weekly at 01:00" in page.text

            # Replace it from the web form.
            saved = client.post(
                "/scrape_schedule", data={"cadence": "every_other_day", "run_at": "03:30", "snatch": "true"}
            )
            assert saved.status_code == 200
            assert "every other day at 03:30" in saved.text and "Update schedule" in saved.text
            job = scheduler.get_job(SCRAPE_SCHEDULE_JOB_ID)
            assert job is not None and job is not restored and "every other day" in job.name
            with Session(isolated_db_engine) as session:
                rows = session.exec(SQLModel.metadata.tables["scrapeschedule"].select()).all()
            assert len(rows) == 1 and rows[0].cadence == "every_other_day" and rows[0].snatch_enabled

            # The JSON API sees the same schedule, with the job's next run time.
            api = client.get("/api/scrape_schedule")
            assert api.status_code == 200
            assert api.json()["schedule"]["cadence"] == "every_other_day"
            assert api.json()["next_run_timestamp"] == int(job.next_run_time.timestamp())

            # Remove it from the web button: row + job gone, the JSON API reports nothing configured.
            removed = client.delete("/scrape_schedule")
            assert removed.status_code == 200 and "No scheduled scrape is configured" in removed.text
            assert scheduler.get_job(SCRAPE_SCHEDULE_JOB_ID) is None
            assert client.get("/api/scrape_schedule").status_code == 404
