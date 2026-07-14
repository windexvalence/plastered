from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlmodel import Session, and_, col, desc, select

from plastered.api.api_models import (
    AdhocSearchResult,
    RunHistoryItem,
    RunHistoryListResponse,
    RunHistoryPageResponse,
    RunHistoryRow,
)
from plastered.db.db_models import (
    Failed,
    Grabbed,
    Matched,
    RecDownloadBatch,
    ScraperRun,
    SearchRecord,
    Skipped,
    Status,
    get_engine,
)
from plastered.db.db_utils import complete_rec_download_batch, get_result_by_id, increment_rec_download_batch

if TYPE_CHECKING:
    from collections.abc import Sequence

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


def get_scraper_run_action(run_id: int, session: Session) -> ScraperRun | None:
    """Returns the `ScraperRun` for `run_id` (used by the scraper-run progress UI), or `None` if it does not exist."""
    return session.exec(select(ScraperRun).where(ScraperRun.id == run_id)).first()


def get_latest_rec_download_batch(session: Session, scraper_run_id: int) -> RecDownloadBatch | None:
    """Returns the most recent post-hoc download batch for a scraper run (drives the recs-section progress UI)."""
    return session.exec(
        select(RecDownloadBatch)
        .where(RecDownloadBatch.scraper_run_id == scraper_run_id)
        .order_by(desc(RecDownloadBatch.id))
    ).first()


def scraper_run_recs_action(
    session: Session, run_id: int
) -> tuple[ScraperRun, list[RunHistoryItem], RecDownloadBatch | None] | None:
    """
    Returns (scraper run, its pulled recs, latest download batch) for the run-history scraper recs sub-fragment, or
    `None` if the run does not exist.
    """
    run = session.exec(select(ScraperRun).where(ScraperRun.id == run_id)).first()
    if run is None:
        return None
    return run, _scraper_run_recs(session=session, run=run), get_latest_rec_download_batch(session, run_id)


def scraper_run_matched_rec_ids(session: Session, run: ScraperRun) -> list[int]:
    """Returns the ids of a scraper run's recs that found a match but were not downloaded (status MATCHED)."""
    return [
        item.searchrecord.id
        for item in _scraper_run_recs(session=session, run=run)
        if item.searchrecord.status == Status.MATCHED and item.searchrecord.id is not None
    ]


def run_rec_download_batch_action(release_searcher: ReleaseSearcher, batch_id: int, search_ids: Sequence[int]) -> None:
    """
    Background action: snatch each selected scraper rec's recorded match, sequentially, through the shared throttled
    RED snatch client (so the per-API rate limit of <=1 request / red_api_seconds_between_calls is preserved). Updates
    the RecDownloadBatch progress as it goes and marks it COMPLETED at the end.
    """
    for search_id in search_ids:
        with Session(get_engine()) as session:
            record = session.exec(select(SearchRecord).where(SearchRecord.id == search_id)).first()
            matched = session.exec(select(Matched).where(Matched.m_result_id == search_id)).first()
        # Only snatch recs that are still an un-downloaded match (ignore anything already grabbed/changed meanwhile).
        if record is not None and matched is not None and record.status == Status.MATCHED:
            release_searcher.snatch_recorded_match(search_id=search_id, matched=matched)
        increment_rec_download_batch(batch_id=batch_id)
    complete_rec_download_batch(batch_id=batch_id)


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


def _scraper_run_recs(session: Session, run: ScraperRun) -> list[RunHistoryItem]:
    """Returns the per-rec `RunHistoryItem`s a scraper run produced (scraper-created records within its time window)."""
    upper_bound = run.finished_timestamp if run.finished_timestamp is not None else 2**63 - 1
    records = session.exec(
        select(SearchRecord)
        .where(
            col(SearchRecord.is_manual).is_(False),
            SearchRecord.submit_timestamp >= run.submit_timestamp,
            SearchRecord.submit_timestamp <= upper_bound,
        )
        .order_by(desc(SearchRecord.submit_timestamp))
    ).all()
    return [_run_history_item_for_record(session=session, record=record) for record in records]


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
    Returns one page of run-history rows for the HTML accordion view: ad-hoc searches plus LFM scraper runs (each run
    is one row; its scraper-created per-rec records are nested, not listed at the top level). Defaults: newest-first,
    <=50 per page. Supports a status filter, a free-text artist/entity filter, sort direction, and a search_id lookup —
    all of which target ad-hoc rows; scraper runs are shown only in the unfiltered default view.
    """
    page = max(page, 1)
    page_size = min(max(page_size, 1), _MAX_RUN_HISTORY_PAGE_SIZE)

    # Top-level ad-hoc rows: user-initiated searches only (scraper-created records nest under their run).
    adhoc_conditions: list[Any] = [col(SearchRecord.is_manual).is_(True)]
    if status_filter is not None:
        adhoc_conditions.append(SearchRecord.status == status_filter)
    if search_id is not None:
        adhoc_conditions.append(SearchRecord.id == search_id)
    if query:
        like = f"%{query}%"
        adhoc_conditions.append(or_(col(SearchRecord.artist).ilike(like), col(SearchRecord.entity).ilike(like)))
    adhoc_records = session.exec(select(SearchRecord).where(and_(*adhoc_conditions))).all()

    # Scraper runs appear only in the unfiltered default browse (they have no artist/entity for text/status filtering).
    include_scraper_runs = status_filter is None and not query and search_id is None
    scraper_runs = session.exec(select(ScraperRun)).all() if include_scraper_runs else []

    merged: list[tuple[str, int, Any]] = [("adhoc", record.submit_timestamp, record) for record in adhoc_records] + [
        ("scraper", run.submit_timestamp, run) for run in scraper_runs
    ]
    merged.sort(key=lambda entry: entry[1], reverse=sort_desc)

    total_count = len(merged)
    page_entries = merged[(page - 1) * page_size : (page - 1) * page_size + page_size]
    rows: list[RunHistoryRow] = []
    for kind, sort_timestamp, obj in page_entries:
        if kind == "adhoc":
            rows.append(
                RunHistoryRow(
                    kind="adhoc", sort_timestamp=sort_timestamp, adhoc=_run_history_item_for_record(session, obj)
                )
            )
        else:
            rows.append(
                RunHistoryRow(
                    kind="scraper",
                    sort_timestamp=sort_timestamp,
                    scraper=obj,
                    scraper_recs=_scraper_run_recs(session=session, run=obj),
                    download_batch=get_latest_rec_download_batch(session, obj.id),
                )
            )
    return RunHistoryPageResponse(
        rows=rows,
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
    )


def _default_since_ts() -> int:  # pragma: no cover
    """Returns the default timestamp 6 months ago for date-ranged default queries."""
    return int((datetime.now(tz=UTC) - timedelta(days=180)).timestamp())
