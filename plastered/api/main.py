"""Entrypoint for the plastered server and FastAPI application."""

import logging
import os
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
from plastered.version import get_project_version

# Required for uvicorn logging to be at all configurable: https://github.com/Kludex/uvicorn/issues/945#issuecomment-819692145
logging.basicConfig(level=get_app_settings().server.log_level)
_LOGGER = logging.getLogger(__name__)


# Set up some application state stuff
@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    # Startup events: Initialize stuff
    _LOGGER.info("Running fastapi app lifespan startup ...")
    db_startup()
    singleton = get_lifespan_singleton()
    app.state.lifespan_singleton = singleton
    cast("LifespanSingleton", app.state.lifespan_singleton)
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
# TODO (maybe / later): switch to this block template lib: https://github.com/tataraba/simplesite/blob/main/docs/04_Chapter_4.md#the-python-stuff
# templates = Jinja2Blocks(directory=_TEMPLATES_DIRPATH)


if __name__ == "__main__":
    app_settings = get_app_settings()
    log_level = app_settings.server.log_level
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    uvicorn.run(
        "plastered.api.main:fastapi_app",
        host=app_settings.server.host,
        port=app_settings.server.port,
        reload=True,
        reload_dirs=["./static", "./templates"],
        reload_includes=["*.css", "*.js", "*.html", "*.template", "*.j2"],
        log_level=log_level.lower(),
        workers=app_settings.server.workers,
    )
