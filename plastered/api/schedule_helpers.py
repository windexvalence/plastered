"""Helpers for the scheduled-scrape flow of the HTMX web router (form parsing + fragment template context)."""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING, Any, Final

from fastapi import HTTPException, status
from pydantic import ValidationError
from tzlocal import get_localzone_name

from plastered.api.api_models import ScrapeScheduleRequest
from plastered.db.db_models import ScrapeCadence
from plastered.models import EntityType

if TYPE_CHECKING:
    from plastered.api.api_models import ScrapeScheduleResponse

SCRAPE_SCHEDULE_FRAGMENT: Final[str] = "fragments/scrape_schedule_fragment.html"
_DEFAULT_RUN_AT: Final[str] = "03:00"
_UNKNOWN_TIMEZONE: Final[str] = "unknown"


def build_scrape_schedule_request_from_form(
    cadence: str, run_at: str, rec_type: str | None = None, snatch: bool = False
) -> ScrapeScheduleRequest:
    """
    Builds a `ScrapeScheduleRequest` from the scraper page's schedule form (`run_at` is the time input's `HH:MM`).
    Raises an `HTTPException` (422) when the provided values fail validation.
    """
    try:
        run_time = time.fromisoformat(run_at.strip())
        return ScrapeScheduleRequest(
            cadence=ScrapeCadence(cadence),
            hour=run_time.hour,
            minute=run_time.minute,
            rec_type=EntityType(rec_type) if rec_type else None,
            snatch=snatch,
        )
    except (ValidationError, ValueError) as ex:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(ex)) from ex


def scrape_schedule_template_context(schedule: ScrapeScheduleResponse | None) -> dict[str, Any]:
    """Template context for the scraper page's scheduled-scrape section (`SCRAPE_SCHEDULE_FRAGMENT`)."""
    current = schedule.schedule if schedule is not None else None
    return {
        "schedule": schedule,
        "cadences": list(ScrapeCadence),
        "cadence_label": ScrapeCadence(current.cadence).display_name if current is not None else None,
        "run_at": f"{current.hour:02d}:{current.minute:02d}" if current is not None else _DEFAULT_RUN_AT,
        # tzlocal yields None (despite its `str` annotation) when no zone name is discoverable, e.g. a
        # bind-mounted /etc/localtime that is a regular file rather than a symlink.
        "system_timezone": get_localzone_name() or _UNKNOWN_TIMEZONE,
    }
