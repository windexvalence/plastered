from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from plastered.db.db_models import get_engine


def _get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session


SessionDep = Annotated[Session, Depends(_get_session)]
