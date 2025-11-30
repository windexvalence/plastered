from __future__ import annotations

import logging
import os
from typing import Any, Final

from sqlmodel import Session, SQLModel, select

from plastered.db.db_models import ENGINE, Failed, FailReason, Grabbed, SearchRecord, Skipped, SkipReason, Status
from plastered.models.types import EncodingEnum, EntityType, FormatEnum, MediaEnum
from plastered.utils.exceptions import MissingDatabaseRecordException

_LOGGER = logging.getLogger(__name__)
_DB_TEST_MODE: Final[bool] = os.getenv("DB_TEST_MODE", "false") == "true"


def db_startup() -> None:
    table_classes: list[type[SQLModel]] = [SearchRecord, Skipped, Grabbed, Failed]
    _LOGGER.info("Creating metadata for DB tables ...")
    for tbl_cls in table_classes:
        tbl_cls.metadata.create_all(ENGINE)
    # SQLModel.metadata.create_all(ENGINE)
    if _DB_TEST_MODE:  # pragma: no cover
        _create_test_tables(table_classes=table_classes)
    _LOGGER.info("DB tables metadata creation complete.")


def add_record(session: Session, model_inst: SQLModel) -> None:
    """Helper for running a `session.add()`, `session.commit()` and `session.refresh()`."""
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
    with Session(ENGINE) as session:
        _LOGGER.debug("Querying SearchRecord record ...")
        result_record = get_result_by_id(search_id=search_id, session=session)
        _LOGGER.debug(f"Updating status of SearchRecord record (id={search_id}) ...")
        result_record.status = status
        session.add(result_record)
        _LOGGER.debug(f"Creating associated Status record for SearchRecord record (id={search_id}) ...")
        status_record: Failed | Grabbed | Skipped | None = None
        if status == status.FAILED:
            status_record = Failed(f_result_id=search_id, **status_model_kwargs)
        elif status == status.GRABBED:
            status_record = Grabbed(g_result_id=search_id, **status_model_kwargs)
        elif status == status.SKIPPED:
            status_record = Skipped(s_result_id=search_id, **status_model_kwargs)
        else:
            raise ValueError(  # pragma: no cover
                f"Unexpected status: '{str(status)}'. Should be one of {[Status.FAILED, Status.GRABBED, Status.SKIPPED]}"
            )
        session.add(status_record)
        session.commit()
        _LOGGER.debug(f"Finished updating status of SearchRecord record (id={search_id}) ...")


def get_result_by_id(search_id: int | None, session: Session | None = None) -> SearchRecord:
    if search_id is None:
        raise MissingDatabaseRecordException(search_id)

    if not session:
        with Session(ENGINE) as sesh:
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

    SQLModel.metadata.drop_all(ENGINE)
    for tbl_cls in table_classes:
        tbl_cls.metadata.create_all(ENGINE)
    session = Session(ENGINE)
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
