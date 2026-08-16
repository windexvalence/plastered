from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, cast

from fastapi import Depends, Request
from sqlmodel import Session

from plastered.config.app_settings import AppSettings
from plastered.db.db_models import get_engine
from plastered.models import RedUserDetails
from plastered.release_search.release_searcher import ReleaseSearcher

if TYPE_CHECKING:
    from collections.abc import Generator


def _get_session() -> Generator[Session]:
    with Session(get_engine()) as session:
        yield session


SessionDep = Annotated[Session, Depends(_get_session)]


def get_app_settings_from_state(request: Request) -> AppSettings:
    """Return the `AppSettings` loaded at startup (see `plastered.api.app`)."""
    return cast("AppSettings", request.app.state.app_settings)


AppSettingsDep = Annotated[AppSettings, Depends(get_app_settings_from_state)]


def get_release_searcher_from_state(request: Request) -> ReleaseSearcher:
    """Return the shared `ReleaseSearcher` built at startup (see `plastered.api.app`)."""
    return cast("ReleaseSearcher", request.app.state.release_searcher)


ReleaseSearcherDep = Annotated[ReleaseSearcher, Depends(get_release_searcher_from_state)]


def get_red_user_details_from_state(request: Request) -> RedUserDetails:
    """Return the `RedUserDetails` fetched from RED at startup (see `plastered.api.app`)."""
    return cast("RedUserDetails", request.app.state.red_user_details)


RedUserDetailsDep = Annotated[RedUserDetails, Depends(get_red_user_details_from_state)]
