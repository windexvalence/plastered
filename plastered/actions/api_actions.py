import logging
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import desc, select, Session

from plastered.config.app_settings import AppSettings
from plastered.db.db_models import SearchRun, RunState
from plastered.models.manual_search_models import ManualSearch
from plastered.models.search_item import SearchItem
from plastered.release_search.release_searcher import ReleaseSearcher


_LOGGER = logging.getLogger(__name__)


def run_history_action(
    since_timestamp: int,
    session: Session,
) -> list[SearchRun]:
    manual_runs = session.exec(
        select(SearchRun)
        .where(SearchRun.submit_timestamp >= since_timestamp)
        .offset(0)
        .order_by(desc(SearchRun.submit_timestamp))
        .limit(100)
    ).all()
    return manual_runs


async def manual_search_action(
    session: Session, app_settings: AppSettings, search_run: SearchRun, mbid: str | None = None
) -> dict[str, Any]:
    """
    Action for executing a manual search + snatch of a given Album or track.
    Returns `True` if found and snatched the release, `False` otherwise.
    """
    db_search_run = SearchRun.model_validate(search_run)
    session.add(db_search_run)
    session.commit()
    session.refresh(db_search_run)
    db_manual_run_id = db_search_run.id
    snatched_search_item: SearchItem | None = None
    try:
        with ReleaseSearcher(app_settings=app_settings) as release_searcher:
            release_searcher.manual_search(
                manual_query=ManualSearch(
                    entity_type=db_search_run.entity_type,
                    artist=db_search_run.artist,
                    entity=db_search_run.entity,
                    mbid=mbid,
                )
            )
            snatched_search_item = release_searcher.get_snatched_manual_search_item()
    except Exception as ex:
        msg = f"Uncaught exception raised during manual search attempt: {type(ex)}"
        _LOGGER.error(msg, exc_info=True)
    finally:
        mr_db = session.get(SearchRun, db_manual_run_id)
        if not mr_db:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual run not found")
        if snatched_search_item is not None:
            mr_db.state = RunState.SUCCESS
            mr_db.tid = snatched_search_item.torrent_entry.torrent_id
        else:
            mr_db.state = RunState.FAILED
        session.add(mr_db)
        session.commit()
        session.refresh(mr_db)
    return mr_db.model_dump()
