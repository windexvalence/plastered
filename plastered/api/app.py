"""FastAPI application factory for the plastered server. Launched via the `plastered run` CLI (`plastered/main.py`)."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from plastered.api.auth_sessions import SessionTokenStore
from plastered.api.constants import STATIC_DIRPATH
from plastered.api.middleware import LoginProtectionMiddleware
from plastered.api.routes import auth_router, plastered_api_router, plastered_web_router
from plastered.config.app_settings import get_app_settings
from plastered.db.db_models import get_engine
from plastered.db.db_utils import db_startup
from plastered.release_search.release_searcher import ReleaseSearcher
from plastered.utils.http_clients import RedAPIClient
from plastered.version import get_project_version

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

_LOGGER = logging.getLogger(__name__)


def create_fastapi_app() -> FastAPI:
    """Returns the configured plastered FastAPI app instance. This is the function `uvicorn` calls."""
    # https://fastapi.tiangolo.com/tutorial/sql-databases/#create-models
    fastapi_app = FastAPI(version=get_project_version(), lifespan=_app_lifespan)
    fastapi_app.mount("/static", StaticFiles(directory=os.fspath(STATIC_DIRPATH)), name="static")
    # The token store lives on `app.state` at construction time (not in the lifespan) so each app instance gets a
    # fresh registry.
    fastapi_app.state.token_store = SessionTokenStore()
    fastapi_app.add_middleware(LoginProtectionMiddleware)
    fastapi_app.include_router(auth_router)
    fastapi_app.include_router(plastered_api_router)
    fastapi_app.include_router(plastered_web_router)
    return fastapi_app


@asynccontextmanager
async def _app_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Context manager used by FastAPI for initializing application-scoped singletons (held on `app.state`, read by
    the routes via the accessor dependencies in `plastered.api.fastapi_dependencies`)."""
    _LOGGER.debug("Running fastapi app lifespan startup ...")
    app_settings = get_app_settings()
    app.state.app_settings = app_settings

    db_startup()
    # Build the shared RED client + `ReleaseSearcher` once at startup (reused across API calls) rather than per
    # request. The searcher is given the shared client and pre-fetched user details (and builds the remaining API
    # clients itself), so it builds fresh per-run state on each search call.
    red_api_client = RedAPIClient(app_settings=app_settings)
    app.state.red_user_details = red_api_client.get_red_user_details()
    app.state.release_searcher = ReleaseSearcher(
        app_settings=app_settings, red_user_details=app.state.red_user_details, red_api_client=red_api_client
    )
    yield
    # Shutdown events: Clean up stuff
    _LOGGER.warning("Server shutting down ...")
    app.state.release_searcher.close_clients()
    # Dispose the cached engine so its pooled SQLite connections are closed and the DB file is released cleanly
    # (sessions are all context-managed, so no connections are checked out by this point).
    get_engine().dispose()
