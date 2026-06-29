from __future__ import annotations

import logging
import os
from typing import Any, Final

from sqlmodel import Session, SQLModel, select

from plastered.db.db_models import (
    Failed,
    FailReason,
    Grabbed,
    Matched,
    ScraperRun,
    SearchProgress,
    SearchRecord,
    Skipped,
    SkipReason,
    Status,
    get_engine,
)
from plastered.models.types import EncodingEnum, EntityType, FormatEnum, MediaEnum
from plastered.utils.exceptions import MissingDatabaseRecordException

_LOGGER = logging.getLogger(__name__)
_DB_TEST_MODE: Final[bool] = os.getenv("DB_TEST_MODE", "false").lower() == "true"


def db_startup() -> None:
    table_classes: list[type[SQLModel]] = [
        SearchRecord,
        Skipped,
        Grabbed,
        Failed,
        Matched,
        SearchProgress,
        ScraperRun,
    ]
    _LOGGER.info("Creating metadata for DB tables ...")
    for tbl_cls in table_classes:
        tbl_cls.metadata.create_all(get_engine())
    if _DB_TEST_MODE:  # pragma: no cover
        _create_test_tables(table_classes=table_classes)
    _LOGGER.info("DB tables metadata creation complete.")


def add_record(model_inst: SQLModel, session: Session | None = None) -> None:
    """Helper for running a `session.add()`, `session.commit()` and `session.refresh()`."""
    if not session:
        with Session(get_engine()) as session:
            _add_record(session=session, model_inst=model_inst)
    else:
        _add_record(session=session, model_inst=model_inst)


def _add_record(session: Session, model_inst: SQLModel) -> None:
    session.add(model_inst)
    session.commit()
    session.refresh(model_inst)


def set_result_status(search_id: int | None, status: Status, status_model_kwargs: dict[str, Any]) -> None:
    """
    Takes in the given `SearchRecord` ID, updates the corresponding record's `status`, and creates a corresponding row in the
    associated status table. status_row_kwargs is a dict of kwargs for the status ORM instance.
    """
    if search_id is None:
        raise MissingDatabaseRecordException(search_id)
    with Session(get_engine()) as session:
        _LOGGER.debug("Querying SearchRecord record ...")
        result_record = get_result_by_id(search_id=search_id, session=session)
        _LOGGER.debug(f"Updating status of SearchRecord record (id={search_id}) ...")
        result_record.status = status
        session.add(result_record)
        _LOGGER.debug(f"Creating associated Status record for SearchRecord record (id={search_id}) ...")
        status_record: Failed | Grabbed | Skipped | Matched | None = None
        if status == status.FAILED:
            status_record = Failed(f_result_id=search_id, **status_model_kwargs)
        elif status == status.GRABBED:
            status_record = Grabbed(g_result_id=search_id, **status_model_kwargs)
        elif status == status.SKIPPED:
            status_record = Skipped(s_result_id=search_id, **status_model_kwargs)
        elif status == status.MATCHED:
            status_record = Matched(m_result_id=search_id, **status_model_kwargs)
        else:
            raise ValueError(  # pragma: no cover
                f"Unexpected status: '{str(status)}'. Should be one of "
                f"{[Status.FAILED, Status.GRABBED, Status.SKIPPED, Status.MATCHED]}"
            )
        session.add(status_record)
        session.commit()
        _LOGGER.debug(f"Finished updating status of SearchRecord record (id={search_id}) ...")


def upsert_search_progress(search_id: int | None, current_pref: int, total_prefs: int, current_pref_label: str) -> None:
    """
    Records (insert-or-update) the live progress of an in-flight ad-hoc search — the RED format preference currently
    being searched — so the result UI can render a progress bar. A no-op when `search_id` is None.
    """
    if search_id is None:  # pragma: no cover
        return
    with Session(get_engine()) as session:
        progress = session.exec(select(SearchProgress).where(SearchProgress.sp_result_id == search_id)).first()
        if progress is None:
            progress = SearchProgress(sp_result_id=search_id)
        progress.current_pref = current_pref
        progress.total_prefs = total_prefs
        progress.current_pref_label = current_pref_label
        session.add(progress)
        session.commit()


def create_scraper_run(snatch_enabled: bool, rec_types: list[str], submit_timestamp: int) -> int:
    """Creates an `IN_PROGRESS` ScraperRun row and returns its id."""
    run = ScraperRun(
        submit_timestamp=submit_timestamp, snatch_enabled=snatch_enabled, rec_types=",".join(rec_types)
    )
    with Session(get_engine()) as session:
        session.add(run)
        session.commit()
        session.refresh(run)
    if run.id is None:  # pragma: no cover
        raise MissingDatabaseRecordException(run.id)
    return run.id


def update_scraper_run(run_id: int, **fields: Any) -> None:
    """Updates the given fields on the ScraperRun row identified by `run_id`."""
    with Session(get_engine()) as session:
        run = session.exec(select(ScraperRun).where(ScraperRun.id == run_id)).first()
        if run is None:  # pragma: no cover
            raise MissingDatabaseRecordException(run_id)
        for field_name, value in fields.items():
            setattr(run, field_name, value)
        session.add(run)
        session.commit()


def get_result_by_id(search_id: int | None, session: Session | None = None) -> SearchRecord:
    if search_id is None:
        raise MissingDatabaseRecordException(search_id)

    if not session:
        with Session(get_engine()) as sesh:
            result_rows = _get_rows(s=sesh, search_id=search_id)
    else:
        result_rows = _get_rows(s=session, search_id=search_id)

    if result_rows:
        return result_rows[0]
    raise MissingDatabaseRecordException(search_id)  # pragma: no cover


def _get_rows(s: Session, search_id: int) -> list[SearchRecord] | None:  # pragma: no cover
    return list(s.exec(select(SearchRecord).where(SearchRecord.id == search_id)).all())


def _create_test_tables(table_classes: list[type[SQLModel]]) -> None:  # pragma: no cover
    from datetime import datetime

    SQLModel.metadata.drop_all(get_engine())
    for tbl_cls in table_classes:
        tbl_cls.metadata.create_all(get_engine())
    session = Session(get_engine())
    _LOGGER.info("Test mode detected. Initializing test records ...")
    submit_ts = int(datetime.now().timestamp())
    in_prog_res = SearchRecord(
        is_manual=True,
        entity_type=EntityType.ALBUM,
        artist="Fake Artist 1",
        entity="Fake Album X",
        submit_timestamp=submit_ts,
        status=Status.IN_PROGRESS,
        media=MediaEnum.CD,
        encoding=EncodingEnum.LOSSLESS,
        format=FormatEnum.FLAC,
    )
    skipped_res = SearchRecord(
        is_manual=True,
        entity_type=EntityType.ALBUM,
        artist="Fake Artist 2",
        entity="Fake Album Y",
        submit_timestamp=submit_ts,
        status=Status.SKIPPED,
        media=MediaEnum.VINYL,
        encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS,
        format=FormatEnum.FLAC,
    )
    failed_res = SearchRecord(
        is_manual=True,
        entity_type=EntityType.ALBUM,
        artist="Fake Artist 3",
        entity="Fake Album Z",
        submit_timestamp=submit_ts,
        status=Status.FAILED,
        media=MediaEnum.WEB,
        encoding=EncodingEnum.MP3_320,
        format=FormatEnum.MP3,
    )
    grabbed_res = SearchRecord(
        is_manual=True,
        entity_type=EntityType.TRACK,
        artist="Fake Artist 4",
        entity="Fake Track A",
        submit_timestamp=submit_ts,
        status=Status.GRABBED,
        media=MediaEnum.SACD,
        encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS,
        format=FormatEnum.FLAC,
    )
    result_models = [in_prog_res, skipped_res, failed_res, grabbed_res]
    session.add_all(result_models)
    session.commit()
    for rm in result_models:
        session.refresh(rm)
    # for res in [in_prog_res, skipped_res, failed_res, grabbed_res]:
    #     add_record(session=session, model_inst=res)

    skip = Skipped(s_result_id=skipped_res.id, skip_reason=SkipReason.ABOVE_MAX_ALLOWED_SIZE)
    failed = Failed(f_result_id=failed_res.id, fail_reason=FailReason.RED_API_REQUEST_ERROR)
    grabbed = Grabbed(
        g_result_id=grabbed_res.id, fl_token_used=False, snatch_path="/some/fake/downloads/69420.torrent", tid=69420
    )
    for meta_record in [skip, failed, grabbed]:
        add_record(session=session, model_inst=meta_record)

    _LOGGER.info("Test DB records initialized")
