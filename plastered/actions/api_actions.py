import logging
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlmodel import Session, desc, select

from plastered.config.app_settings import AppSettings
from plastered.db.db_models import SearchRun
from plastered.db.db_utils import add_record
from plastered.models.manual_search_models import ManualSearch
from plastered.models.search_item import SearchItem
from plastered.release_search.release_searcher import ReleaseSearcher

_LOGGER = logging.getLogger(__name__)


def run_history_action(since_timestamp: int, session: Session) -> list[SearchRun]:
    manual_runs = session.exec(
        select(SearchRun)
        .where(SearchRun.submit_timestamp >= since_timestamp)
        .offset(0)
        .order_by(desc(SearchRun.submit_timestamp))
        .limit(100)
    ).all()
    return list(manual_runs)


def inspect_run_action(run_id: int, session: Session) -> SearchRun | None:
    """Returns the SearchRun record associated with the provided `run_id`, otherwise return `None`."""
    result_rows = list(session.exec(select(SearchRun).where(SearchRun.id == run_id)).all())
    if result_rows:
        return result_rows[0]
    return None


async def manual_search_action(
    session: Session, app_settings: AppSettings, search_run: SearchRun, mbid: str | None = None
) -> dict[str, Any]:
    """
    Action for executing a manual search + snatch of a given Album or track.
    Returns JSON serialized value of SearchResult if one is found.
    """
    try:
        db_search_run = SearchRun.model_validate(search_run)
    except ValidationError as ex:  # pragma: no cover
        msg = f"Bad search_run model provided. Failed validation with following errors: {ex.errors()}"
        _LOGGER.error(msg, exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from ex
    add_record(session=session, model_inst=db_search_run)
    db_manual_run_id = db_search_run.id
    search_item: SearchItem | None = None
    try:
        with ReleaseSearcher(app_settings=app_settings) as release_searcher:
            release_searcher.manual_search(
                manual_search_instance=ManualSearch(
                    entity_type=db_search_run.entity_type,
                    artist=db_search_run.artist,
                    entity=db_search_run.entity,
                    mbid=mbid,
                )
            )
            search_item = release_searcher.get_finalized_manual_search_item()
    except Exception as ex:  # pragma: no cover
        msg = f"Uncaught exception raised during manual search attempt: {type(ex)}"
        _LOGGER.error(msg, exc_info=True)
        raise ex
    finally:
        if not search_item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SearchItem not found")
        if not (search_result := search_item.search_result):  # pragma: no cover
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SearchResult not found")
        search_result.search_run_id = db_manual_run_id
        add_record(session=session, model_inst=search_result)
    return search_result.model_dump()
