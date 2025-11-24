import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import Row
from sqlmodel import Session, desc, select

from plastered.config.app_settings import AppSettings
from plastered.db.db_models import Failed, Grabbed, Result, Skipped, Status
from plastered.db.db_utils import get_result_by_id
from plastered.release_search.release_searcher import ReleaseSearcher

_LOGGER = logging.getLogger(__name__)


def run_history_action(since_timestamp: int, session: Session, final_state: Status | None = None) -> list[Row]:
    """Queries the list of run SearchRun and/or SearchResult records matching the input criteria."""
    rows = session.exec(
        select(Result, Skipped, Failed, Grabbed)
        .outerjoin(Skipped, Result.id == Skipped.s_result_id)  # type: ignore[arg-type]
        .outerjoin(Failed, Result.id == Failed.f_result_id)  # type: ignore[arg-type]
        .outerjoin(Grabbed, Result.id == Grabbed.g_result_id)  # type: ignore[arg-type]
        # .where(Result.submit_timestamp >= since_timestamp)
        .order_by(desc(Result.submit_timestamp))
    ).all()
    return list(rows)  # type: ignore[arg-type]


def inspect_run_action(run_id: int, session: Session) -> Result | None:
    """Returns the SearchRun record associated with the provided `run_id`, otherwise return `None`."""
    result_rows = list(session.exec(select(Result).where(Result.id == run_id)).all())
    if result_rows:
        return result_rows[0]
    return None


async def manual_search_action(app_settings: AppSettings, search_id: int, mbid: str | None = None) -> dict[str, Any]:
    """
    Action for executing a manual search + snatch of a given Album or track.
    Returns JSON serialized value of SearchResult if one is found.
    """
    search_result: Result | None = None
    try:
        with ReleaseSearcher(app_settings=app_settings) as release_searcher:
            release_searcher.manual_search(search_id=search_id, mbid=mbid)
    except Exception as ex:  # pragma: no cover
        msg = f"Uncaught exception raised during manual search attempt: {type(ex)}"
        _LOGGER.error(msg, exc_info=True)
        raise ex
    search_result = get_result_by_id(search_id=search_id)
    if not search_result:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SearchResult not found")
    return search_result.model_dump()
