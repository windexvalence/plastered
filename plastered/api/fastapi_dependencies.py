from collections.abc import Generator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlmodel import Session

from plastered.config.app_settings import AppSettings
from plastered.db.db_models import get_engine


def _get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session


SessionDep = Annotated[Session, Depends(_get_session)]


def get_app_settings_from_state(request: Request) -> AppSettings:
    """Return the `AppSettings` loaded at startup (see `plastered.api.app`)."""
    return cast("AppSettings", request.app.state.lifespan_singleton.app_settings)


AppSettingsDep = Annotated[AppSettings, Depends(get_app_settings_from_state)]
