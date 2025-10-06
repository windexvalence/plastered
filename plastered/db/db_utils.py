import logging
from pathlib import Path
from typing import Final, Generator, TYPE_CHECKING

from sqlmodel import Field, Session, SQLModel, create_engine, select

from plastered.config.app_settings import get_app_settings, AppSettings
from plastered.db.db_models import SearchRun


if TYPE_CHECKING:
    from sqlalchemy.engine.base import Engine


_LOGGER = logging.getLogger(__name__)
_DB_FILEPATH: Final[Path] = get_app_settings().get_db_filepath()
_SQLITE_URL: Final[str] = f"sqlite:///{_DB_FILEPATH}"
_ENGINE: Final["Engine"] = create_engine(_SQLITE_URL, connect_args={"check_same_thread": False})


def get_session() -> Generator[Session, None, None]:
    _LOGGER.debug("Initializing db session ...")
    with Session(_ENGINE) as session:
        yield session


def db_startup() -> None:
    _LOGGER.info("Creating metadata for DB tables ...")
    SearchRun.metadata.create_all(_ENGINE)
    _LOGGER.info("DB tables metadata creation complete.")
