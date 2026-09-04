"""
Scheduled LFM scraper runs. The persisted `ScrapeSchedule` row (at most one) is the source of truth: the app lifespan
re-registers the single APScheduler job from it on every startup (`restore_scrape_schedule`), the routes replace or
remove it (`set_scrape_schedule` / `clear_scrape_schedule`), and the job itself re-reads it on each run.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from starlette.concurrency import run_in_threadpool

from plastered.actions.api_actions import get_scraper_run_action
from plastered.actions.common_actions import run_lfm_scraper
from plastered.api.api_models import ScrapeScheduleResponse
from plastered.db.db_models import ScrapeCadence
from plastered.db.db_utils import (
    create_scraper_run,
    delete_scrape_schedule,
    get_scrape_schedule,
    update_scrape_schedule,
    upsert_scrape_schedule,
)

if TYPE_CHECKING:
    from datetime import tzinfo

    from apscheduler.job import Job
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.base import BaseTrigger
    from sqlmodel import Session

    from plastered.api.api_models import ScrapeScheduleRequest
    from plastered.config.app_settings import AppSettings
    from plastered.db.db_models import ScraperRun, ScrapeSchedule
    from plastered.release_search.release_searcher import ReleaseSearcher

_LOGGER = logging.getLogger(__name__)

SCRAPE_SCHEDULE_JOB_ID: Final[str] = "scheduled_lfm_scrape"
# A due run still fires if the process was busy/asleep for up to this long past its scheduled time (APScheduler's
# default grace of 1s would silently drop it as a misfire).
_MISFIRE_GRACE_SECONDS: Final[int] = 60 * 60
_CADENCE_INTERVAL_DAYS: Final[dict[ScrapeCadence, int]] = {
    ScrapeCadence.DAILY: 1,
    ScrapeCadence.EVERY_OTHER_DAY: 2,
    ScrapeCadence.WEEKLY: 7,
    ScrapeCadence.EVERY_OTHER_WEEK: 14,
}


def _now_ts() -> int:
    return int(datetime.now(tz=UTC).timestamp())


def first_run_datetime(hour: int, minute: int, timezone: tzinfo, now: datetime | None = None) -> datetime:
    """Returns the next occurrence, strictly after `now`, of the given wall-clock time in `timezone`."""
    current = (now if now is not None else datetime.now(tz=UTC)).astimezone(timezone)
    candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= current:
        candidate += timedelta(days=1)
    return candidate


def build_scrape_schedule_trigger(schedule: ScrapeSchedule, timezone: tzinfo) -> BaseTrigger:
    """
    Builds the APScheduler trigger for `schedule`. The interval cadences fire every N days counted from the schedule's
    first run, so every-other-day / every-other-week keep their phase across server restarts. Monthly fires on the
    first run's day of the month; days 29-31 fall back to the last day of each month so no month is skipped.
    """
    start = datetime.fromtimestamp(schedule.start_timestamp, tz=UTC).astimezone(timezone)
    if schedule.cadence == ScrapeCadence.MONTHLY:
        day = str(start.day) if start.day <= 28 else "last"
        return CronTrigger(day=day, hour=schedule.hour, minute=schedule.minute, start_date=start, timezone=timezone)
    return IntervalTrigger(days=_CADENCE_INTERVAL_DAYS[schedule.cadence], start_date=start, timezone=timezone)


def register_scrape_schedule_job(
    scheduler: AsyncIOScheduler, schedule: ScrapeSchedule, app_settings: AppSettings, release_searcher: ReleaseSearcher
) -> Job:
    """(Re-)registers the single scheduled-scrape job for `schedule`, replacing any previously registered one."""
    return scheduler.add_job(
        run_scheduled_scrape,
        trigger=build_scrape_schedule_trigger(schedule=schedule, timezone=scheduler.timezone),
        id=SCRAPE_SCHEDULE_JOB_ID,
        name=f"Scheduled LFM scrape ({schedule.cadence.display_name})",
        replace_existing=True,
        misfire_grace_time=_MISFIRE_GRACE_SECONDS,
        coalesce=True,
        kwargs={"app_settings": app_settings, "release_searcher": release_searcher},
    )


def restore_scrape_schedule(
    scheduler: AsyncIOScheduler, app_settings: AppSettings, release_searcher: ReleaseSearcher
) -> None:
    """Startup hook: registers the scheduled-scrape job from the persisted schedule row, if one is configured."""
    schedule = get_scrape_schedule()
    if schedule is None:
        _LOGGER.info("No scheduled LFM scrape is configured.")
        return
    register_scrape_schedule_job(
        scheduler=scheduler, schedule=schedule, app_settings=app_settings, release_searcher=release_searcher
    )
    _LOGGER.info(
        f"Restored the scheduled LFM scrape ({schedule.cadence.display_name} at "
        f"{schedule.hour:02d}:{schedule.minute:02d} server time)."
    )


def set_scrape_schedule(
    scheduler: AsyncIOScheduler,
    app_settings: AppSettings,
    release_searcher: ReleaseSearcher,
    schedule_request: ScrapeScheduleRequest,
) -> ScrapeScheduleResponse:
    """Saves `schedule_request` as the scrape schedule (replacing any existing one) and (re-)registers its job."""
    first_run = first_run_datetime(
        hour=schedule_request.hour, minute=schedule_request.minute, timezone=scheduler.timezone
    )
    schedule = upsert_scrape_schedule(
        cadence=schedule_request.cadence,
        hour=schedule_request.hour,
        minute=schedule_request.minute,
        rec_type=schedule_request.rec_type,
        snatch_enabled=schedule_request.snatch,
        start_timestamp=int(first_run.timestamp()),
        created_timestamp=_now_ts(),
        last_run_id=None,
        last_run_timestamp=None,
    )
    job = register_scrape_schedule_job(
        scheduler=scheduler, schedule=schedule, app_settings=app_settings, release_searcher=release_searcher
    )
    _LOGGER.info(f"Saved the scheduled LFM scrape ({job.name}); first run at {first_run.isoformat()}.")
    return _to_response(schedule=schedule, job=job, last_run=None)


def clear_scrape_schedule(scheduler: AsyncIOScheduler) -> None:
    """Removes the scrape schedule (its row and its job). A no-op when none is configured."""
    delete_scrape_schedule()
    if scheduler.get_job(SCRAPE_SCHEDULE_JOB_ID) is not None:
        scheduler.remove_job(SCRAPE_SCHEDULE_JOB_ID)
    _LOGGER.info("Removed the scheduled LFM scrape.")


def get_scrape_schedule_response(scheduler: AsyncIOScheduler, session: Session) -> ScrapeScheduleResponse | None:
    """Returns the configured schedule with its next run time and last scheduled run, or `None` when none is set."""
    schedule = get_scrape_schedule(session=session)
    if schedule is None:
        return None
    last_run = (
        get_scraper_run_action(run_id=schedule.last_run_id, session=session)
        if schedule.last_run_id is not None
        else None
    )
    return _to_response(schedule=schedule, job=scheduler.get_job(SCRAPE_SCHEDULE_JOB_ID), last_run=last_run)


def _to_response(schedule: ScrapeSchedule, job: Job | None, last_run: ScraperRun | None) -> ScrapeScheduleResponse:
    # A job only carries `next_run_time` once the scheduler has started (it is absent on a pending job).
    next_run_time = getattr(job, "next_run_time", None)
    return ScrapeScheduleResponse(
        schedule=schedule,
        next_run_timestamp=int(next_run_time.timestamp()) if next_run_time is not None else None,
        last_run=last_run,
    )


async def run_scheduled_scrape(app_settings: AppSettings, release_searcher: ReleaseSearcher) -> None:
    """
    The scheduled-scrape job. Runs a full LFM scraper run off the event loop, exactly like a manual run submitted from
    the scraper page. The schedule row is re-read at run time so its rec type / download options always apply.
    """
    await run_in_threadpool(_run_scheduled_scrape, app_settings, release_searcher)


def _run_scheduled_scrape(app_settings: AppSettings, release_searcher: ReleaseSearcher) -> None:
    schedule = get_scrape_schedule()
    if schedule is None:
        _LOGGER.warning("The scheduled LFM scrape fired but no schedule is configured; skipping.")
        return
    rec_types_override = [schedule.rec_type] if schedule.rec_type is not None else None
    effective_rec_types = (
        [schedule.rec_type.value] if schedule.rec_type is not None else app_settings.lfm.rec_types_to_scrape
    )
    now_ts = _now_ts()
    run_id = create_scraper_run(
        snatch_enabled=schedule.snatch_enabled, rec_types=effective_rec_types, submit_timestamp=now_ts
    )
    update_scrape_schedule(last_run_id=run_id, last_run_timestamp=now_ts)
    _LOGGER.info(f"Starting the scheduled LFM scrape (scraper run {run_id}) ...")
    try:
        run_lfm_scraper(
            app_settings=app_settings,
            release_searcher=release_searcher,
            run_id=run_id,
            rec_types_to_scrape_override=rec_types_override,
            snatch_enabled=schedule.snatch_enabled,
        )
    except Exception as ex:
        # `run_lfm_scraper` has already marked the run FAILED and logged the traceback.
        _LOGGER.error(f"The scheduled LFM scrape (scraper run {run_id}) failed: {ex}")
