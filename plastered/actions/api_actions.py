from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status
from sqlmodel import Session, and_, desc, select

from plastered.api.api_models import RunHistoryItem, RunHistoryListResponse
from plastered.db.db_models import Failed, Grabbed, SearchRecord, Skipped, Status
from plastered.db.db_utils import get_result_by_id
from plastered.release_search.release_searcher import ReleaseSearcher

if TYPE_CHECKING:
    from plastered.config.app_settings import AppSettings
    from plastered.models import RedUserDetails

_LOGGER = logging.getLogger(__name__)


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


async def manual_search_action(
    app_settings: AppSettings, red_user_details: RedUserDetails, search_id: int, **kwargs: Any
) -> dict[str, Any]:
    """
    Action for executing a manual search + snatch of a given Album or track.
    Returns JSON serialized value of SearchRecord if one is found.
    """
    search_result: SearchRecord | None = None
    try:
        with ReleaseSearcher(
            app_settings=app_settings,
            red_user_details=red_user_details,
            red_api_client=kwargs.get("red_api_client"),
            red_snatch_client=kwargs.get("red_snatch_client"),
            lfm_client=kwargs.get("lfm_client"),
            musicbrainz_client=kwargs.get("musicbrainz_client"),
        ) as release_searcher:
            release_searcher.manual_search(search_id=search_id, mbid=kwargs.get("mbid"))
    except Exception as ex:  # pragma: no cover
        msg = f"Uncaught exception raised during manual search attempt: {type(ex)}"
        _LOGGER.error(msg, exc_info=True)
        raise ex
    search_result = get_result_by_id(search_id=search_id)
    if not search_result:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SearchRecord not found")
    return search_result.model_dump()


def _default_since_ts() -> int:  # pragma: no cover
    """Returns the default timestamp 6 months ago for date-ranged default queries."""
    return int((datetime.now(tz=UTC) - timedelta(days=180)).timestamp())
