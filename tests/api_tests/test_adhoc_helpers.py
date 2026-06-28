from unittest.mock import MagicMock

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlmodel import Session, select

from plastered.api.adhoc_helpers import build_adhoc_request_from_form, schedule_adhoc_search
from plastered.api.api_models import AdhocSearchRequest
from plastered.db.db_models import SearchRecord, Status
from plastered.models.adhoc_search_models import AdhocSearch
from plastered.release_search.release_searcher import ReleaseSearcher


def test_schedule_adhoc_search_creates_record_and_schedules(mock_session: Session) -> None:
    req = AdhocSearchRequest(search=AdhocSearch(artist="Some Artist", release="Some Album"))
    # The api_tests autouse fixture stubs BackgroundTasks.add_task, so assert against a dedicated mock instead.
    background_tasks = MagicMock(spec=BackgroundTasks)
    release_searcher = MagicMock(spec=ReleaseSearcher)

    search_id = schedule_adhoc_search(
        session=mock_session, background_tasks=background_tasks, release_searcher=release_searcher, req=req
    )

    assert search_id == 1
    background_tasks.add_task.assert_called_once()
    stored = mock_session.exec(select(SearchRecord).where(SearchRecord.id == search_id)).one()
    assert stored.is_manual is True
    assert stored.artist == "Some Artist"
    assert stored.entity == "Some Album"
    assert stored.status == Status.IN_PROGRESS


def test_build_adhoc_request_from_form_blank_fields_become_none() -> None:
    req = build_adhoc_request_from_form(artist="Some Artist", release="Some Album", track="  ", mbid="", snatch=True)
    assert req.search.release == "Some Album"
    assert req.search.track is None
    assert req.search.mbid is None
    assert req.overrides is not None and req.overrides.snatch is True


def test_build_adhoc_request_from_form_parses_max_size() -> None:
    req = build_adhoc_request_from_form(artist="Some Artist", release="Some Album", max_size_gb="12.5")
    assert req.overrides is not None and req.overrides.max_size_gb == 12.5


def test_build_adhoc_request_from_form_invalid_raises_422() -> None:
    with pytest.raises(HTTPException) as exc_info:
        build_adhoc_request_from_form(artist="Some Artist")  # neither release nor track
    assert exc_info.value.status_code == 422
