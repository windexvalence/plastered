"""Entrypoint for the plastered server and FastAPI application."""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from plastered.api.constants import STATIC_DIRPATH
from plastered.api.lifespan_resources import LifespanSingleton, get_lifespan_singleton
from plastered.api.routes import plastered_api_router, plastered_web_router
from plastered.config.app_settings import get_app_settings
from plastered.db.db_utils import db_startup
from plastered.utils.log_utils import create_stream_log_handler
from plastered.version import get_project_version

# When running as the server, log via the builtin logging module (a plain stdlib StreamHandler) rather than rich.
# Required for uvicorn logging to be at all configurable: https://github.com/Kludex/uvicorn/issues/945#issuecomment-819692145
logging.basicConfig(level=get_app_settings().server.log_level, handlers=[create_stream_log_handler()])
_LOGGER = logging.getLogger(__name__)


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


# https://fastapi.tiangolo.com/tutorial/sql-databases/#create-models
fastapi_app = FastAPI(version=get_project_version(), lifespan=_app_lifespan)
fastapi_app.mount("/static", StaticFiles(directory=os.fspath(STATIC_DIRPATH)), name="static")
fastapi_app.include_router(plastered_api_router)
fastapi_app.include_router(plastered_web_router)


if __name__ == "__main__":
    server_config = get_app_settings().server
    uvicorn.run(
        "plastered.api.main:fastapi_app",
        host=server_config.host,
        port=server_config.port,
        log_level=server_config.log_level.lower(),
        # Keep the worker count config-driven: RED's per-process rate limit stays globally correct only when this is 1
        # (see ServerConfig). Note uvicorn ignores `workers` when `reload=True`, so this launch path does not reload.
        workers=server_config.workers,
    )
