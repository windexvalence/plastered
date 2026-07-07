"""FastAPI application factory for the plastered server. Launched via the `plastered run` CLI (`plastered/main.py`)."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from plastered.api.constants import STATIC_DIRPATH
from plastered.api.lifespan_resources import LifespanSingleton, get_lifespan_singleton
from plastered.api.routes import plastered_api_router, plastered_web_router
from plastered.db.db_utils import db_startup
from plastered.version import get_project_version

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

_LOGGER = logging.getLogger(__name__)


def create_fastapi_app() -> FastAPI:
    """Returns the configured plastered FastAPI app instance. This is the function `uvicorn` calls."""
    # https://fastapi.tiangolo.com/tutorial/sql-databases/#create-models
    fastapi_app = FastAPI(version=get_project_version(), lifespan=_app_lifespan)
    fastapi_app.mount("/static", StaticFiles(directory=os.fspath(STATIC_DIRPATH)), name="static")
    fastapi_app.include_router(plastered_api_router)
    fastapi_app.include_router(plastered_web_router)
    return fastapi_app


@asynccontextmanager
async def _app_lifespan(app: FastAPI) -> AsyncGenerator[dict[str, LifespanSingleton], None]:
    """Context manager used by FastAPI for initializing application-scoped singletons."""
    _LOGGER.debug("Running fastapi app lifespan startup ...")
    db_startup()
    singleton = get_lifespan_singleton()
    app.state.lifespan_singleton = singleton
    cast("LifespanSingleton", app.state.lifespan_singleton)
    # The yielded mapping becomes each request's `request.state`, which the routes read as `lifespan_singleton`.
    # https://github.com/fastapi/fastapi/discussions/9664#discussioncomment-11170662
    yield {"lifespan_singleton": singleton}
    # Shutdown events: Clean up stuff
    _LOGGER.info("Server shutting down ...")
    app.state.lifespan_singleton.shutdown()
