"""Shared helpers for the ad-hoc release search flow, used by both the JSON API router and the HTMX web router."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlmodel import select

from plastered.actions.api_actions import adhoc_search_action
from plastered.api.api_models import AdhocSearchRequest
from plastered.config.app_settings import RedSearchOverrides
from plastered.db.db_models import AdhocRequest, SearchRecord, Status
from plastered.db.db_utils import add_record
from plastered.models import AdhocSearch, EntityType

if TYPE_CHECKING:
    from fastapi import BackgroundTasks
    from sqlmodel import Session

    from plastered.release_search.release_searcher import ReleaseSearcher

_LOGGER = logging.getLogger(__name__)


def _clean(value: str | None) -> str | None:
    """Normalize an HTML form value: trim whitespace and treat the empty string as `None` (an unset optional field)."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def build_adhoc_request_from_form(
    artist: str,
    release: str | None = None,
    track: str | None = None,
    mbid: str | None = None,
    release_type: str | None = None,
    release_year: str | None = None,
    record_label: str | None = None,
    catalog_number: str | None = None,
    snatch: bool = False,
    max_size_gb: str | None = None,
) -> AdhocSearchRequest:
    """
    Builds an `AdhocSearchRequest` from the flat (string) fields of the web search form, treating blank inputs as unset.
    Raises an `HTTPException` (422) when the provided values fail model validation.
    """
    try:
        search = AdhocSearch(
            artist=artist,
            release=_clean(release),
            track=_clean(track),
            mbid=_clean(mbid),
            release_type=_clean(release_type),  # type: ignore[arg-type]
            release_year=_clean(release_year),  # type: ignore[arg-type]
            record_label=_clean(record_label),
            catalog_number=_clean(catalog_number),
        )
        cleaned_max_size = _clean(max_size_gb)
        overrides = RedSearchOverrides(
            snatch=snatch, max_size_gb=float(cleaned_max_size) if cleaned_max_size is not None else None
        )
    except (ValidationError, ValueError) as ex:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ex)) from ex
    return AdhocSearchRequest(search=search, overrides=overrides)


def schedule_adhoc_search(
    session: Session, background_tasks: BackgroundTasks, release_searcher: ReleaseSearcher, req: AdhocSearchRequest
) -> int:
    """
    Creates the `IN_PROGRESS` `SearchRecord` for an ad-hoc search and schedules the search to run in the background.
    Returns the new record's id, which the client polls for the eventual result.
    """
    record = SearchRecord(
        is_manual=True,
        artist=req.search.artist,
        entity=req.search.get_human_readable_entity_str(),
        entity_type=req.search.entity_type,
        submit_timestamp=req.search.submit_timestamp,
        status=Status.IN_PROGRESS,
    )
    add_record(session=session, model_inst=record)
    if (search_id := record.id) is None:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to create search record")
    add_record(session=session, model_inst=AdhocRequest(search_id=search_id, request_json=req.model_dump_json()))
    _LOGGER.debug(f"Scheduling ad-hoc search id={search_id} for {req.search.artist!r} / {req.search.entity_type}")
    background_tasks.add_task(
        func=adhoc_search_action,
        release_searcher=release_searcher,
        adhoc_search=req.search,
        search_id=search_id,
        overrides=req.overrides,
    )
    return search_id


def load_adhoc_request(session: Session, search_id: int) -> AdhocSearchRequest | None:
    """
    Returns the stored request of an ad-hoc search. Returns `None` when none is stored (a scraper-created record, or
    an ad-hoc search submitted before requests were stored) or when the stored JSON no longer validates against the
    current request models (the JSON is never migrated), so callers can fall back to rebuilding it from the record.
    """
    row = session.exec(select(AdhocRequest).where(AdhocRequest.search_id == search_id)).first()
    if row is None:
        return None
    try:
        return AdhocSearchRequest.model_validate_json(row.request_json)
    except ValidationError:
        _LOGGER.warning(
            f"Stored request of ad-hoc search id={search_id} no longer validates; ignoring it.", exc_info=True
        )
        return None


def _request_from_record(record: SearchRecord) -> AdhocSearchRequest:
    """Rebuilds the request of an ad-hoc search that has no stored request from its record: artist + album/track."""
    is_album = record.entity_type == EntityType.ALBUM
    search = AdhocSearch(
        artist=record.artist, release=record.entity if is_album else None, track=None if is_album else record.entity
    )
    return AdhocSearchRequest(search=search)


def retry_adhoc_search(
    session: Session, background_tasks: BackgroundTasks, release_searcher: ReleaseSearcher, search_id: int
) -> int:
    """
    Re-submits the request of the ad-hoc search identified by `search_id` as a new search (same request, fresh submit
    timestamp) and returns the new search's id. Raises an `HTTPException` (404) when no ad-hoc search has that id.
    """
    record = session.exec(select(SearchRecord).where(SearchRecord.id == search_id)).first()
    if record is None or not record.is_manual:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No ad-hoc search record matching search_id={search_id}."
        )
    req = load_adhoc_request(session=session, search_id=search_id) or _request_from_record(record)
    # Re-validate without the original timestamp so the model's default factory stamps the new submission.
    search = AdhocSearch.model_validate(req.search.model_dump(exclude={"submit_timestamp"}))
    _LOGGER.debug(f"Retrying ad-hoc search id={search_id} for {search.artist!r} / {search.entity_type}")
    return schedule_adhoc_search(
        session=session,
        background_tasks=background_tasks,
        release_searcher=release_searcher,
        req=AdhocSearchRequest(search=search, overrides=req.overrides),
    )
