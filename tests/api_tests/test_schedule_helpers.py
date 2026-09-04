from unittest.mock import patch

from fastapi import HTTPException
import pytest

from plastered.api.api_models import ScrapeScheduleRequest, ScrapeScheduleResponse
from plastered.api.schedule_helpers import build_scrape_schedule_request_from_form, scrape_schedule_template_context
from plastered.db.db_models import ScrapeCadence, ScrapeSchedule
from plastered.models.types import EntityType


@pytest.mark.parametrize(
    "form_kwargs, expected",
    [
        (
            {"cadence": "daily", "run_at": "03:00"},
            ScrapeScheduleRequest(cadence=ScrapeCadence.DAILY, hour=3, minute=0, rec_type=None, snatch=False),
        ),
        (
            {"cadence": "every_other_week", "run_at": " 23:45 ", "rec_type": "album", "snatch": True},
            ScrapeScheduleRequest(
                cadence=ScrapeCadence.EVERY_OTHER_WEEK, hour=23, minute=45, rec_type=EntityType.ALBUM, snatch=True
            ),
        ),
        # Browsers may submit seconds; the blank rec type means "all (per config)".
        (
            {"cadence": "monthly", "run_at": "04:15:00", "rec_type": ""},
            ScrapeScheduleRequest(cadence=ScrapeCadence.MONTHLY, hour=4, minute=15, rec_type=None, snatch=False),
        ),
    ],
)
def test_build_scrape_schedule_request_from_form(form_kwargs: dict, expected: ScrapeScheduleRequest) -> None:
    assert build_scrape_schedule_request_from_form(**form_kwargs) == expected


@pytest.mark.parametrize(
    "form_kwargs",
    [
        {"cadence": "hourly", "run_at": "03:00"},  # not a pre-defined cadence
        {"cadence": "daily", "run_at": "3pm"},  # not an HH:MM time
        {"cadence": "daily", "run_at": "25:00"},  # out-of-range hour
        {"cadence": "daily", "run_at": "03:00", "rec_type": "artist"},  # not a rec type
    ],
)
def test_build_scrape_schedule_request_from_form_invalid(form_kwargs: dict) -> None:
    with pytest.raises(HTTPException) as exc_info:
        build_scrape_schedule_request_from_form(**form_kwargs)
    assert exc_info.value.status_code == 422


def test_scrape_schedule_template_context_unconfigured() -> None:
    context = scrape_schedule_template_context(None)
    assert context["schedule"] is None
    assert context["cadences"] == list(ScrapeCadence)
    assert context["cadence_label"] is None
    assert context["run_at"] == "03:00"


def test_scrape_schedule_template_context_configured() -> None:
    response = ScrapeScheduleResponse(
        schedule=ScrapeSchedule(
            id=1,
            cadence=ScrapeCadence.EVERY_OTHER_DAY,
            hour=7,
            minute=5,
            snatch_enabled=True,
            start_timestamp=1759680000,
            created_timestamp=1759670000,
        )
    )
    context = scrape_schedule_template_context(response)
    assert context["schedule"] is response
    assert context["cadence_label"] == "every other day"
    assert context["run_at"] == "07:05"
