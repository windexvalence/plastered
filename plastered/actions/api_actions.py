import logging
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import Row
from sqlmodel import Session, desc, select

from plastered.config.app_settings import AppSettings
from plastered.db.db_models import Failed, Grabbed, Result, Skipped, Status
from plastered.db.db_utils import add_record
from plastered.models.manual_search_models import ManualSearch
from plastered.models.search_item import SearchItem
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


async def manual_search_action(
    session: Session, app_settings: AppSettings, result: Result, mbid: str | None = None
) -> dict[str, Any]:
    """
    Action for executing a manual search + snatch of a given Album or track.
    Returns JSON serialized value of SearchResult if one is found.
    """
    try:
        db_initial_result = Result.model_validate(result)
    except ValidationError as ex:  # pragma: no cover
        msg = f"Bad search_run model provided. Failed validation with following errors: {ex.errors()}"
        _LOGGER.error(msg, exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from ex
    add_record(session=session, model_inst=db_initial_result)
    result_id = db_initial_result.id
    search_item: SearchItem | None = None
    try:
        with ReleaseSearcher(app_settings=app_settings) as release_searcher:
            release_searcher.manual_search(
                manual_search_instance=ManualSearch(
                    entity_type=db_initial_result.entity_type,
                    artist=db_initial_result.artist,
                    entity=db_initial_result.entity,
                    mbid=mbid,
                )
            )
            search_item = release_searcher.get_finalized_manual_search_item(result_id=result_id)
    except Exception as ex:  # pragma: no cover
        msg = f"Uncaught exception raised during manual search attempt: {type(ex)}"
        _LOGGER.error(msg, exc_info=True)
        raise ex
    if not search_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SearchItem not found")
    if not (search_result := search_item.search_result):  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SearchResult not found")
    return search_result.model_dump()
