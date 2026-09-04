from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import anyio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytest

from plastered.actions.schedule_actions import (
    SCRAPE_SCHEDULE_JOB_ID,
    build_scrape_schedule_trigger,
    clear_scrape_schedule,
    first_run_datetime,
    get_scrape_schedule_response,
    register_scrape_schedule_job,
    restore_scrape_schedule,
    run_scheduled_scrape,
    set_scrape_schedule,
)
from plastered.api.api_models import ScrapeScheduleRequest
from plastered.config.app_settings import AppSettings
from plastered.db.db_models import ScrapeCadence, ScraperRun, ScrapeSchedule
from plastered.models.types import EntityType
from plastered.release_search.release_searcher import ReleaseSearcher

_TZ = ZoneInfo("America/New_York")
_MODULE = "plastered.actions.schedule_actions"


def _schedule(**overrides: Any) -> ScrapeSchedule:
    fields: dict[str, Any] = dict(
        id=1,
        cadence=ScrapeCadence.DAILY,
        hour=3,
        minute=0,
        rec_type=None,
        snatch_enabled=False,
        start_timestamp=int(datetime(2026, 1, 15, 3, 0, tzinfo=_TZ).timestamp()),
        created_timestamp=int(datetime(2026, 1, 14, 12, 0, tzinfo=_TZ).timestamp()),
    )
    fields.update(overrides)
    return ScrapeSchedule(**fields)


@pytest.mark.parametrize(
    "now, hour, minute, expected",
    [
        # Later today -> today.
        (datetime(2026, 1, 14, 12, 0, tzinfo=_TZ), 15, 30, datetime(2026, 1, 14, 15, 30, tzinfo=_TZ)),
        # Already passed today -> tomorrow.
        (datetime(2026, 1, 14, 12, 0, tzinfo=_TZ), 3, 0, datetime(2026, 1, 15, 3, 0, tzinfo=_TZ)),
        # Exactly now -> tomorrow (strictly after now).
        (datetime(2026, 1, 14, 12, 0, tzinfo=_TZ), 12, 0, datetime(2026, 1, 15, 12, 0, tzinfo=_TZ)),
        # `now` given in another zone is converted into the target zone first.
        (datetime(2026, 1, 14, 17, 0, tzinfo=UTC), 12, 30, datetime(2026, 1, 14, 12, 30, tzinfo=_TZ)),
    ],
)
def test_first_run_datetime(now: datetime, hour: int, minute: int, expected: datetime) -> None:
    actual = first_run_datetime(hour=hour, minute=minute, timezone=_TZ, now=now)
    assert actual == expected
    assert actual.tzinfo == _TZ


def test_first_run_datetime_defaults_to_now() -> None:
    before = datetime.now(tz=_TZ)
    actual = first_run_datetime(hour=3, minute=0, timezone=_TZ)
    assert actual > before
    assert actual - before <= timedelta(days=1)
    assert (actual.hour, actual.minute, actual.second) == (3, 0, 0)


@pytest.mark.parametrize(
    "cadence, expected_days",
    [
        (ScrapeCadence.DAILY, 1),
        (ScrapeCadence.EVERY_OTHER_DAY, 2),
        (ScrapeCadence.WEEKLY, 7),
        (ScrapeCadence.EVERY_OTHER_WEEK, 14),
    ],
)
def test_build_scrape_schedule_trigger_interval_cadences(cadence: ScrapeCadence, expected_days: int) -> None:
    schedule = _schedule(cadence=cadence)
    trigger = build_scrape_schedule_trigger(schedule=schedule, timezone=_TZ)
    assert isinstance(trigger, IntervalTrigger)
    assert trigger.interval == timedelta(days=expected_days)
    assert trigger.start_date == datetime(2026, 1, 15, 3, 0, tzinfo=_TZ)
    # First fire from the anchor is the anchor itself; the phase is kept when computing from a later `now`.
    assert trigger.get_next_fire_time(None, datetime(2026, 1, 14, 0, 0, tzinfo=_TZ)) == trigger.start_date
    later_now = datetime(2026, 1, 15, 3, 1, tzinfo=_TZ)
    assert trigger.get_next_fire_time(None, later_now) == trigger.start_date + timedelta(days=expected_days)


@pytest.mark.parametrize(
    "start, expected_day_field",
    [
        (datetime(2026, 1, 15, 3, 0, tzinfo=_TZ), "15"),
        (datetime(2026, 1, 28, 3, 0, tzinfo=_TZ), "28"),
        (datetime(2026, 1, 31, 3, 0, tzinfo=_TZ), "last"),
    ],
)
def test_build_scrape_schedule_trigger_monthly(start: datetime, expected_day_field: str) -> None:
    schedule = _schedule(cadence=ScrapeCadence.MONTHLY, hour=3, minute=45, start_timestamp=int(start.timestamp()))
    trigger = build_scrape_schedule_trigger(schedule=schedule, timezone=_TZ)
    assert isinstance(trigger, CronTrigger)
    assert f"day='{expected_day_field}'" in str(trigger)
    assert "hour='3'" in str(trigger) and "minute='45'" in str(trigger)
    # No month is skipped: February (28 days) still gets a run.
    february_fire = trigger.get_next_fire_time(None, datetime(2026, 2, 1, 0, 0, tzinfo=_TZ))
    assert (
        february_fire is not None and february_fire.month == 2 and (february_fire.hour, february_fire.minute) == (3, 45)
    )


async def _paused_scheduler() -> AsyncIOScheduler:
    """A started-but-paused scheduler: jobs get real next-run times but nothing fires."""
    scheduler = AsyncIOScheduler(timezone=_TZ)
    scheduler.start(paused=True)
    return scheduler


async def _stop(scheduler: AsyncIOScheduler) -> None:
    scheduler.shutdown(wait=False)
    # The shutdown is dispatched onto the event loop; let it run.
    await anyio.sleep(0)
    assert not scheduler.running


@pytest.mark.anyio
async def test_register_restore_and_clear_scrape_schedule_job(valid_app_settings: AppSettings) -> None:
    scheduler = await _paused_scheduler()
    searcher = MagicMock(spec=ReleaseSearcher)
    try:
        # Nothing configured -> nothing registered.
        with patch(f"{_MODULE}.get_scrape_schedule", return_value=None):
            restore_scrape_schedule(scheduler=scheduler, app_settings=valid_app_settings, release_searcher=searcher)
        assert scheduler.get_job(SCRAPE_SCHEDULE_JOB_ID) is None

        schedule = _schedule(cadence=ScrapeCadence.WEEKLY, snatch_enabled=True)
        with patch(f"{_MODULE}.get_scrape_schedule", return_value=schedule):
            restore_scrape_schedule(scheduler=scheduler, app_settings=valid_app_settings, release_searcher=searcher)
        job = scheduler.get_job(SCRAPE_SCHEDULE_JOB_ID)
        assert job is not None
        assert job.func is run_scheduled_scrape
        assert job.kwargs == {"app_settings": valid_app_settings, "release_searcher": searcher}
        assert isinstance(job.trigger, IntervalTrigger) and job.trigger.interval == timedelta(days=7)
        assert job.next_run_time is not None
        assert "weekly" in job.name

        # Re-registering replaces the single job rather than adding a second one.
        replaced = register_scrape_schedule_job(
            scheduler=scheduler,
            schedule=_schedule(cadence=ScrapeCadence.MONTHLY),
            app_settings=valid_app_settings,
            release_searcher=searcher,
        )
        assert [j.id for j in scheduler.get_jobs()] == [SCRAPE_SCHEDULE_JOB_ID]
        assert isinstance(replaced.trigger, CronTrigger)

        with patch(f"{_MODULE}.delete_scrape_schedule") as mock_delete:
            clear_scrape_schedule(scheduler=scheduler)
            assert scheduler.get_job(SCRAPE_SCHEDULE_JOB_ID) is None
            # Clearing again (no job registered) is a no-op that still clears the row.
            clear_scrape_schedule(scheduler=scheduler)
        assert mock_delete.call_count == 2
    finally:
        await _stop(scheduler)


@pytest.mark.anyio
async def test_set_scrape_schedule(valid_app_settings: AppSettings) -> None:
    scheduler = await _paused_scheduler()
    searcher = MagicMock(spec=ReleaseSearcher)
    request = ScrapeScheduleRequest(
        cadence=ScrapeCadence.EVERY_OTHER_DAY, hour=4, minute=15, rec_type=EntityType.TRACK, snatch=True
    )
    try:
        with patch(
            f"{_MODULE}.upsert_scrape_schedule", side_effect=lambda **kw: ScrapeSchedule(id=1, **kw)
        ) as mock_upsert:
            before = datetime.now(tz=UTC)
            response = set_scrape_schedule(
                scheduler=scheduler,
                app_settings=valid_app_settings,
                release_searcher=searcher,
                schedule_request=request,
            )
        saved = mock_upsert.call_args.kwargs
        assert saved["cadence"] == ScrapeCadence.EVERY_OTHER_DAY
        assert (saved["hour"], saved["minute"]) == (4, 15)
        assert saved["rec_type"] == EntityType.TRACK and saved["snatch_enabled"] is True
        # A new schedule starts with a clean "last run".
        assert saved["last_run_id"] is None and saved["last_run_timestamp"] is None
        first_run = datetime.fromtimestamp(saved["start_timestamp"], tz=_TZ)
        assert first_run > before and (first_run.hour, first_run.minute) == (4, 15)
        # The job is registered and its first fire is the schedule's first run.
        assert response.schedule.id == 1 and response.last_run is None
        assert response.next_run_timestamp == saved["start_timestamp"]
        assert scheduler.get_job(SCRAPE_SCHEDULE_JOB_ID) is not None
    finally:
        await _stop(scheduler)


def test_get_scrape_schedule_response_none_when_unconfigured() -> None:
    with patch(f"{_MODULE}.get_scrape_schedule", return_value=None):
        assert get_scrape_schedule_response(scheduler=MagicMock(spec=AsyncIOScheduler), session=MagicMock()) is None


@pytest.mark.parametrize("has_last_run", [False, True])
def test_get_scrape_schedule_response(has_last_run: bool) -> None:
    """Without a registered job (e.g. a stopped scheduler) the next run is unknown; the last run is looked up by id."""
    schedule = _schedule(last_run_id=7 if has_last_run else None)
    last_run = ScraperRun(id=7, submit_timestamp=1, snatch_enabled=False, rec_types="album")
    scheduler = MagicMock(spec=AsyncIOScheduler)
    scheduler.get_job.return_value = None
    session = MagicMock()
    with (
        patch(f"{_MODULE}.get_scrape_schedule", return_value=schedule),
        patch(f"{_MODULE}.get_scraper_run_action", return_value=last_run) as mock_get_run,
    ):
        response = get_scrape_schedule_response(scheduler=scheduler, session=session)
    assert response is not None
    assert response.schedule is schedule
    assert response.next_run_timestamp is None
    scheduler.get_job.assert_called_once_with(SCRAPE_SCHEDULE_JOB_ID)
    if has_last_run:
        mock_get_run.assert_called_once_with(run_id=7, session=session)
        assert response.last_run is last_run
    else:
        mock_get_run.assert_not_called()
        assert response.last_run is None


@pytest.mark.anyio
async def test_run_scheduled_scrape_skips_when_unconfigured(valid_app_settings: AppSettings) -> None:
    with (
        patch(f"{_MODULE}.get_scrape_schedule", return_value=None),
        patch(f"{_MODULE}.create_scraper_run") as mock_create_run,
        patch(f"{_MODULE}.run_lfm_scraper") as mock_run,
    ):
        await run_scheduled_scrape(app_settings=valid_app_settings, release_searcher=MagicMock(spec=ReleaseSearcher))
    mock_create_run.assert_not_called()
    mock_run.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "rec_type, expected_rec_types, expected_override",
    [(None, ["album", "track"], None), (EntityType.ALBUM, ["album"], [EntityType.ALBUM])],
)
async def test_run_scheduled_scrape_runs_the_scraper(
    valid_app_settings: AppSettings,
    rec_type: EntityType | None,
    expected_rec_types: list[str],
    expected_override: list[EntityType] | None,
) -> None:
    schedule = _schedule(rec_type=rec_type, snatch_enabled=True)
    searcher = MagicMock(spec=ReleaseSearcher)
    with (
        patch(f"{_MODULE}.get_scrape_schedule", return_value=schedule),
        patch(f"{_MODULE}.create_scraper_run", return_value=42) as mock_create_run,
        patch(f"{_MODULE}.update_scrape_schedule") as mock_update_schedule,
        patch(f"{_MODULE}.run_lfm_scraper") as mock_run,
    ):
        await run_scheduled_scrape(app_settings=valid_app_settings, release_searcher=searcher)
    create_kwargs = mock_create_run.call_args.kwargs
    assert create_kwargs["snatch_enabled"] is True and create_kwargs["rec_types"] == expected_rec_types
    mock_update_schedule.assert_called_once_with(last_run_id=42, last_run_timestamp=create_kwargs["submit_timestamp"])
    mock_run.assert_called_once_with(
        app_settings=valid_app_settings,
        release_searcher=searcher,
        run_id=42,
        rec_types_to_scrape_override=expected_override,
        snatch_enabled=True,
    )


@pytest.mark.anyio
async def test_run_scheduled_scrape_failure_is_logged_not_raised(
    valid_app_settings: AppSettings, caplog: pytest.LogCaptureFixture
) -> None:
    """`run_lfm_scraper` marks the run FAILED itself; the job must not propagate (APScheduler would just log it again)."""
    with (
        patch(f"{_MODULE}.get_scrape_schedule", return_value=_schedule()),
        patch(f"{_MODULE}.create_scraper_run", return_value=42),
        patch(f"{_MODULE}.update_scrape_schedule"),
        patch(f"{_MODULE}.run_lfm_scraper", side_effect=RuntimeError("boom")),
        caplog.at_level("ERROR", logger=_MODULE),
    ):
        await run_scheduled_scrape(app_settings=valid_app_settings, release_searcher=MagicMock(spec=ReleaseSearcher))
    assert "scraper run 42) failed: boom" in caplog.text
