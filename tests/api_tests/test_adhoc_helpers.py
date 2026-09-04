from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlmodel import Session, select

from plastered.api.adhoc_helpers import (
    build_adhoc_request_from_form,
    load_adhoc_request,
    retry_adhoc_search,
    schedule_adhoc_search,
)
from plastered.api.api_models import AdhocSearchRequest
from plastered.config.app_settings import RedSearchOverrides
from plastered.db.db_models import AdhocRequest, SearchRecord, Status
from plastered.models.adhoc_search_models import AdhocSearch
from plastered.models.types import EntityType
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


def _add_record(session: Session, is_manual: bool, entity_type: EntityType = EntityType.ALBUM) -> int:
    record = SearchRecord(
        is_manual=is_manual,
        artist="Some Artist",
        entity="Some Entity",
        entity_type=entity_type,
        submit_timestamp=1,
        status=Status.SKIPPED,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    assert record.id is not None
    return record.id


def test_schedule_adhoc_search_stores_request(mock_session: Session) -> None:
    """The submitted request is persisted verbatim (as JSON) against the new search record, for later retries."""
    req = AdhocSearchRequest(
        search=AdhocSearch(artist="Some Artist", track="Some Track", release_year=1999, submit_timestamp=1),
        overrides=RedSearchOverrides(snatch=True, max_size_gb=2.5),
    )
    search_id = schedule_adhoc_search(
        session=mock_session,
        background_tasks=MagicMock(spec=BackgroundTasks),
        release_searcher=MagicMock(spec=ReleaseSearcher),
        req=req,
    )
    stored = mock_session.exec(select(AdhocRequest).where(AdhocRequest.search_id == search_id)).one()
    assert AdhocSearchRequest.model_validate_json(stored.request_json) == req
    assert load_adhoc_request(session=mock_session, search_id=search_id) == req


def test_load_adhoc_request_missing_returns_none(mock_session: Session) -> None:
    assert load_adhoc_request(session=mock_session, search_id=404) is None


def test_retry_adhoc_search_resubmits_stored_request(mock_session: Session) -> None:
    """A retry schedules a new search with the original request (refinements + overrides) and a fresh timestamp."""
    req = AdhocSearchRequest(
        search=AdhocSearch(artist="Some Artist", track="Some Track", mbid="abc", release_year=1999, submit_timestamp=1),
        overrides=RedSearchOverrides(snatch=True, max_size_gb=2.5),
    )
    release_searcher = MagicMock(spec=ReleaseSearcher)
    original_id = schedule_adhoc_search(
        session=mock_session,
        background_tasks=MagicMock(spec=BackgroundTasks),
        release_searcher=release_searcher,
        req=req,
    )
    background_tasks = MagicMock(spec=BackgroundTasks)
    before = int(datetime.now().timestamp())

    new_id = retry_adhoc_search(
        session=mock_session,
        background_tasks=background_tasks,
        release_searcher=release_searcher,
        search_id=original_id,
    )

    assert new_id != original_id
    new_record = mock_session.exec(select(SearchRecord).where(SearchRecord.id == new_id)).one()
    assert (new_record.artist, new_record.entity, new_record.entity_type, new_record.status) == (
        "Some Artist",
        "Some Track",
        EntityType.TRACK,
        Status.IN_PROGRESS,
    )
    assert new_record.submit_timestamp >= before
    task_kwargs = background_tasks.add_task.call_args.kwargs
    retried_search: AdhocSearch = task_kwargs["adhoc_search"]
    assert retried_search.model_dump(exclude={"submit_timestamp"}) == req.search.model_dump(
        exclude={"submit_timestamp"}
    )
    assert retried_search.submit_timestamp >= before
    assert task_kwargs["overrides"] == req.overrides
    assert task_kwargs["search_id"] == new_id
    # The retried search's own request is stored too, so it can itself be retried.
    assert load_adhoc_request(session=mock_session, search_id=new_id) == AdhocSearchRequest(
        search=retried_search, overrides=req.overrides
    )


@pytest.mark.parametrize("entity_type", [EntityType.ALBUM, EntityType.TRACK])
def test_retry_adhoc_search_rebuilds_request_without_stored_row(mock_session: Session, entity_type: EntityType) -> None:
    """An ad-hoc search stored before requests were persisted is retried from its record's artist + album/track."""
    search_id = _add_record(mock_session, is_manual=True, entity_type=entity_type)
    background_tasks = MagicMock(spec=BackgroundTasks)

    new_id = retry_adhoc_search(
        session=mock_session,
        background_tasks=background_tasks,
        release_searcher=MagicMock(spec=ReleaseSearcher),
        search_id=search_id,
    )

    task_kwargs = background_tasks.add_task.call_args.kwargs
    retried_search: AdhocSearch = task_kwargs["adhoc_search"]
    assert retried_search.artist == "Some Artist"
    assert retried_search.entity_type == entity_type
    expected_names = ("Some Entity", None) if entity_type == EntityType.ALBUM else (None, "Some Entity")
    assert (retried_search.release, retried_search.track) == expected_names
    assert task_kwargs["overrides"] is None
    assert task_kwargs["search_id"] == new_id


def test_retry_adhoc_search_missing_record_raises_404(mock_session: Session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        retry_adhoc_search(
            session=mock_session,
            background_tasks=MagicMock(spec=BackgroundTasks),
            release_searcher=MagicMock(spec=ReleaseSearcher),
            search_id=404,
        )
    assert exc_info.value.status_code == 404


def test_retry_adhoc_search_scraper_record_raises_404(mock_session: Session) -> None:
    """Only ad-hoc (manual) searches can be retried; a scraper-created rec is reported as not found."""
    search_id = _add_record(mock_session, is_manual=False)
    with pytest.raises(HTTPException) as exc_info:
        retry_adhoc_search(
            session=mock_session,
            background_tasks=MagicMock(spec=BackgroundTasks),
            release_searcher=MagicMock(spec=ReleaseSearcher),
            search_id=search_id,
        )
    assert exc_info.value.status_code == 404


def test_retry_adhoc_search_ignores_stored_request_that_no_longer_validates(mock_session: Session) -> None:
    """Stored JSON is never migrated: a row the current models reject is ignored and the record's fields are used."""
    search_id = _add_record(mock_session, is_manual=True)
    stale_row = AdhocRequest(search_id=search_id, request_json='{"search": {"artist": "Old Artist", "bogus": 1}}')
    mock_session.add(stale_row)
    mock_session.commit()
    background_tasks = MagicMock(spec=BackgroundTasks)

    assert load_adhoc_request(session=mock_session, search_id=search_id) is None
    retry_adhoc_search(
        session=mock_session,
        background_tasks=background_tasks,
        release_searcher=MagicMock(spec=ReleaseSearcher),
        search_id=search_id,
    )

    retried_search: AdhocSearch = background_tasks.add_task.call_args.kwargs["adhoc_search"]
    assert (retried_search.artist, retried_search.release) == ("Some Artist", "Some Entity")
