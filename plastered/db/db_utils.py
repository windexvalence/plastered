from __future__ import annotations

import logging
import os
from collections.abc import Generator
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

from sqlmodel import Session, SQLModel

from plastered.db.db_models import ENGINE, Failed, FailReason, Grabbed, Result, Skipped, SkipReason, Status
from plastered.models.types import EncodingEnum, EntityType, FormatEnum, MediaEnum

if TYPE_CHECKING:
    from sqlalchemy import Row


_LOGGER = logging.getLogger(__name__)
_DB_TEST_MODE: Final[bool] = os.getenv("DB_TEST_MODE", "false") == "true"


def get_session() -> Generator[Session, None, None]:
    _LOGGER.debug("Initializing db session ...")
    with Session(ENGINE) as session:
        yield session


def db_startup() -> None:
    table_classes: list[type[SQLModel]] = [Result, Skipped, Grabbed, Failed]
    _LOGGER.info("Creating metadata for DB tables ...")
    for tbl_cls in table_classes:
        tbl_cls.metadata.create_all(ENGINE)
    # SQLModel.metadata.create_all(ENGINE)
    if _DB_TEST_MODE:
        _create_test_tables(table_classes=table_classes)
    _LOGGER.info("DB tables metadata creation complete.")


def add_record(session: Session, model_inst: SQLModel) -> None:
    """Helper for running a `session.add()`, `session.commit()` and `session.refresh()`."""
    session.add(model_inst)
    session.commit()
    session.refresh(model_inst)


def query_rows_to_jinja_context_obj(rows: list[Row]) -> list[dict[str, Any]]:
    """Takes in a SqlAlchemy query result (list of Row objects), and returns a list of stringified dicts."""
    res: list[dict[str, Any]] = []
    for row in rows:
        row_d = row._asdict()
        for k, v in row_d.items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    if isinstance(sv, StrEnum):
                        row_d[k][sk] = str(sv)
        res.append(row_d)
    return res


def _create_test_tables(table_classes: list[SQLModel]) -> None:
    from datetime import datetime

    SQLModel.metadata.drop_all(ENGINE)
    for tbl_cls in table_classes:
        tbl_cls.metadata.create_all(ENGINE)
    session = Session(ENGINE)
    _LOGGER.info("Test mode detected. Initializing test records ...")
    submit_ts = int(datetime.now().timestamp())
    in_prog_res = Result(
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
    skipped_res = Result(
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
    failed_res = Result(
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
    grabbed_res = Result(
        is_manual=True,
        entity_type=EntityType.TRACK,
        artist="Fake Artist 4",
        entity="Fake Track A",
        submit_timestamp=submit_ts,
        status=Status.SUCCESS,
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
