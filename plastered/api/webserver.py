import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Final

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# from jinja2_fragments.fastapi import Jinja2Blocks
from plastered.api.api_routes import plastered_api_router
from plastered.api.constants import STATIC_DIRPATH, TEMPLATES
from plastered.config.app_settings import get_app_settings
from plastered.db.db_utils import db_startup
from plastered.models.types import EntityType
from plastered.version import get_project_version

# Required for uvicorn logging to be at all configurable: https://github.com/Kludex/uvicorn/issues/945#issuecomment-819692145
logging.basicConfig(level=get_app_settings().server.log_level)
_LOGGER = logging.getLogger(__name__)
_HTMX_FILEPATH: Final[Path] = STATIC_DIRPATH / "js" / "htmx-2.0.4.min.js"
_STATIC_IMAGES_DIRPATH: Final[Path] = STATIC_DIRPATH / "images"
# TODO: switch to this block template lib: https://github.com/tataraba/simplesite/blob/main/docs/04_Chapter_4.md#the-python-stuff
# templates = Jinja2Blocks(directory=_TEMPLATES_DIRPATH)


# Set up some application state stuff
@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    # Startup events: Initialize stuff
    _LOGGER.info("Running fastapi app lifespan startup ...")
    db_startup()
    yield
    # Shutdown events: Clean up stuff
    _LOGGER.info("Server shutting down ...")


# https://fastapi.tiangolo.com/tutorial/sql-databases/#create-models
fastapi_app = FastAPI(version=get_project_version(), lifespan=_app_lifespan)
fastapi_app.mount("/static", StaticFiles(directory=os.fspath(STATIC_DIRPATH)), name="static")
fastapi_app.include_router(plastered_api_router)
# fastapi_app.mount(API_URL_PATH_PREFIX, plastered_api_router)


@fastapi_app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(os.fspath(_STATIC_IMAGES_DIRPATH / "favicon.ico"))


# https://fastapi.tiangolo.com/async/#in-a-hurry
@fastapi_app.get("/")
async def root_endpoint(request: Request) -> HTMLResponse:
    _LOGGER.debug(f"htmx_path: {os.fspath(_HTMX_FILEPATH)}")
    return TEMPLATES.TemplateResponse(
        name="index.html", request=request, context={"plastered_version": fastapi_app.version}
    )


# /config
@fastapi_app.get("/config")
async def show_config_endpoint(request: Request) -> HTMLResponse:
    _LOGGER.debug(f"/config endpoint called at {datetime.now().timestamp()}")
    return TEMPLATES.TemplateResponse("config.html", {"request": request})


# /search_form<?entity=(album|track)>
@fastapi_app.get("/search_form")
async def search_form_endpoint(request: Request, entity: EntityType | None = None) -> HTMLResponse:
    if entity is None:
        return TEMPLATES.TemplateResponse("manual_search.html", {"request": request})
    return TEMPLATES.TemplateResponse(
        name="fragments/search_modal.html", request=request, context={"entity": str(entity)}
    )


# /scrape_form
@fastapi_app.get("/scrape_form")
async def scrape_form_endpoint(request: Request) -> HTMLResponse:
    # TODO: have HTMX hit the /api/scrape endpoint following user setup
    return TEMPLATES.TemplateResponse("scrape_form.html", {"request": request})


# /run_history
@fastapi_app.get("/run_history")
async def runs_page(request: Request) -> HTMLResponse:
    # TODO: have HTMX hit the /api/run_history endpoint following user setup
    return TEMPLATES.TemplateResponse("run_history_page.html", {"request": request})


# /result_modal?<final-state-specific query parameters created by HTMX>
@fastapi_app.get("/result_modal")
async def result_modal(request: Request) -> HTMLResponse:
    _LOGGER.debug(f"endpoint /result_modal called with params: {request.query_params}")
    return TEMPLATES.TemplateResponse(
        name="fragments/result_modal.html", request=request, context={"params": request.query_params}
    )


if __name__ == "__main__":
    app_settings = get_app_settings()
    log_level = app_settings.server.log_level
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    uvicorn.run(
        "plastered.api.webserver:fastapi_app",
        host=app_settings.server.host,
        port=app_settings.server.port,
        reload=True,
        reload_dirs=["./static", "./templates"],
        reload_includes=["*.css", "*.js", "*.html", "*.template", "*.j2"],
        log_level=log_level.lower(),
        workers=app_settings.server.workers,
    )
