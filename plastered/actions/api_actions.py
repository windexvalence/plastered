from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlmodel import Session, and_, asc, col, desc, select

from plastered.api.api_models import AdhocSearchResult, RunHistoryItem, RunHistoryListResponse, RunHistoryPageResponse
from plastered.db.db_models import Failed, Grabbed, Matched, SearchProgress, SearchRecord, Skipped, Status
from plastered.db.db_utils import get_result_by_id

if TYPE_CHECKING:
    from plastered.config.app_settings import RedSearchOverrides
    from plastered.models import AdhocSearch
    from plastered.release_search.release_searcher import ReleaseSearcher

_LOGGER = logging.getLogger(__name__)
_MAX_RUN_HISTORY_PAGE_SIZE: int = 50


def run_history_action(
    session: Session,
    since_timestamp: int | None = None,
    final_state: Status | None = None,
    search_id: int | None = None,
) -> RunHistoryListResponse:
    """Queries and returns the list of run search records matching the input criteria."""
    if (since_timestamp or final_state) and search_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="submitted_search_id may not be used in with since_timestamp non-None or final_state non-None",
        )
    since_timestamp = since_timestamp if since_timestamp is not None else _default_since_ts()
    rows = session.exec(
        select(SearchRecord, Skipped, Failed, Grabbed)
        .outerjoin(Skipped, SearchRecord.id == Skipped.s_result_id)  # type: ignore[arg-type]
        .outerjoin(Failed, SearchRecord.id == Failed.f_result_id)  # type: ignore[arg-type]
        .outerjoin(Grabbed, SearchRecord.id == Grabbed.g_result_id)  # type: ignore[arg-type]
        .order_by(desc(SearchRecord.submit_timestamp))
        # https://stackoverflow.com/a/31063911
        .filter(
            and_(
                *(
                    [SearchRecord.submit_timestamp >= since_timestamp]
                    + ([SearchRecord.id == search_id] if search_id else [])
                    + ([SearchRecord.status == final_state] if final_state else [])
                )
            )
        )
    ).all()
    return RunHistoryListResponse(
        runs=[RunHistoryItem.from_sql_row(row=r) for r in rows],  # type: ignore[arg-type]
        since_timestamp=since_timestamp,
    )


def inspect_run_action(run_id: int, session: Session) -> SearchRecord | None:
    """Returns the SearchRun record associated with the provided `run_id`, otherwise return `None`."""
    result_rows = list(session.exec(select(SearchRecord).where(SearchRecord.id == run_id)).all())
    if result_rows:
        return result_rows[0]
    return None


def _run_history_item_for_record(session: Session, record: SearchRecord) -> RunHistoryItem:
    """Builds a `RunHistoryItem` for a single `SearchRecord`, attaching whichever status row(s) exist for it."""
    search_id = record.id
    return RunHistoryItem(
        searchrecord=record,
        grabbed=session.exec(select(Grabbed).where(Grabbed.g_result_id == search_id)).first(),
        failed=session.exec(select(Failed).where(Failed.f_result_id == search_id)).first(),
        skipped=session.exec(select(Skipped).where(Skipped.s_result_id == search_id)).first(),
        matched=session.exec(select(Matched).where(Matched.m_result_id == search_id)).first(),
    )


def run_history_page_action(
    session: Session,
    page: int = 1,
    page_size: int = _MAX_RUN_HISTORY_PAGE_SIZE,
    status_filter: Status | None = None,
    query: str | None = None,
    sort_desc: bool = True,
    search_id: int | None = None,
) -> RunHistoryPageResponse:
    """
    Returns one page of run-history results for the HTML accordion view. Defaults: newest-first, <=50 per page. Supports
    an optional status filter, a free-text filter over artist/entity, sort direction, and a specific search_id lookup.
    """
    page = max(page, 1)
    page_size = min(max(page_size, 1), _MAX_RUN_HISTORY_PAGE_SIZE)
    conditions: list[Any] = []
    if status_filter is not None:
        conditions.append(SearchRecord.status == status_filter)
    if search_id is not None:
        conditions.append(SearchRecord.id == search_id)
    if query:
        like = f"%{query}%"
        conditions.append(or_(col(SearchRecord.artist).ilike(like), col(SearchRecord.entity).ilike(like)))

    count_stmt = select(func.count()).select_from(SearchRecord)
    list_stmt = select(SearchRecord)
    if conditions:
        condition = and_(*conditions)
        count_stmt = count_stmt.where(condition)
        list_stmt = list_stmt.where(condition)

    total_count = int(session.exec(count_stmt).one())
    order_by = desc(SearchRecord.submit_timestamp) if sort_desc else asc(SearchRecord.submit_timestamp)
    records = session.exec(list_stmt.order_by(order_by).offset((page - 1) * page_size).limit(page_size)).all()
    return RunHistoryPageResponse(
        items=[_run_history_item_for_record(session=session, record=record) for record in records],
        page=page,
        page_size=page_size,
        total_count=total_count,
        total_pages=max(1, ceil(total_count / page_size)),
        status_filter=status_filter,
        query=query,
        sort_desc=sort_desc,
        search_id=search_id,
    )


def adhoc_search_action(
    release_searcher: ReleaseSearcher,
    adhoc_search: AdhocSearch,
    search_id: int,
    overrides: RedSearchOverrides | None = None,
) -> dict[str, Any]:
    """
    Background action for executing a single ad-hoc release search (and optional snatch), using the application-wide
    `ReleaseSearcher` initialized once at server startup. Returns the JSON-serialized `SearchRecord` for the run.
    """
    try:
        release_searcher.adhoc_search(adhoc_search=adhoc_search, search_id=search_id, overrides=overrides)
    except Exception as ex:  # pragma: no cover
        msg = f"Uncaught exception raised during ad-hoc search attempt: {type(ex)}"
        _LOGGER.error(msg, exc_info=True)
        raise ex
    search_result = get_result_by_id(search_id=search_id)
    if not search_result:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SearchRecord not found")
    return search_result.model_dump()


def adhoc_snatch_action(
    release_searcher: ReleaseSearcher, search_id: int, session: Session
) -> AdhocSearchResult | None:
    """
    Snatch the release that was previously matched (but not downloaded) for an ad-hoc search-only run. Backs the
    per-result "Download" button. Returns the refreshed `AdhocSearchResult`, or `None` if no record exists for the id.
    A no-op (returns the current result) when the search already downloaded or has no matched release to snatch.
    """
    result = adhoc_result_action(search_id=search_id, session=session)
    if result is None:
        return None
    if result.grabbed is not None or result.matched is None:
        # Already downloaded, or nothing was matched to snatch — nothing to do.
        return result
    release_searcher.snatch_recorded_match(search_id=search_id, matched=result.matched)
    return adhoc_result_action(search_id=search_id, session=session)


def adhoc_result_action(search_id: int, session: Session) -> AdhocSearchResult | None:
    """
    Returns the current `AdhocSearchResult` for the given search id (the search record plus whichever status row has
    been produced so far), or `None` if no record with that id exists. Used by both the JSON result endpoint and the
    HTMX polling fragment to surface matched release(s) and any snatch information once the search completes.
    """
    record = session.exec(select(SearchRecord).where(SearchRecord.id == search_id)).first()
    if record is None:
        return None
    return AdhocSearchResult(
        searchrecord=record,
        matched=session.exec(select(Matched).where(Matched.m_result_id == search_id)).first(),
        grabbed=session.exec(select(Grabbed).where(Grabbed.g_result_id == search_id)).first(),
        failed=session.exec(select(Failed).where(Failed.f_result_id == search_id)).first(),
        skipped=session.exec(select(Skipped).where(Skipped.s_result_id == search_id)).first(),
        progress=session.exec(select(SearchProgress).where(SearchProgress.sp_result_id == search_id)).first(),
    )


def _default_since_ts() -> int:  # pragma: no cover
    """Returns the default timestamp 6 months ago for date-ranged default queries."""
    return int((datetime.now(tz=UTC) - timedelta(days=180)).timestamp())
