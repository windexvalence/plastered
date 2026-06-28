"""Shared helpers for the ad-hoc release search flow, used by both the JSON API router and the HTMX web router."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from pydantic import ValidationError

from plastered.actions.api_actions import adhoc_search_action
from plastered.api.api_models import AdhocSearchRequest
from plastered.config.app_settings import RedSearchOverrides
from plastered.db.db_models import SearchRecord, Status
from plastered.db.db_utils import add_record
from plastered.models import AdhocSearch

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
    _LOGGER.debug(f"Scheduling ad-hoc search id={search_id} for {req.search.artist!r} / {req.search.entity_type}")
    background_tasks.add_task(
        func=adhoc_search_action,
        release_searcher=release_searcher,
        adhoc_search=req.search,
        search_id=search_id,
        overrides=req.overrides,
    )
    return search_id
