import logging
import os
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

from plastered.api.constants import STATIC_DIRPATH, TEMPLATES, Endpoint
from plastered.models.types import EntityType

_LOGGER = logging.getLogger(__name__)
plastered_web_router = APIRouter(prefix="")


@plastered_web_router.get(Endpoint.FAVICON.value.rel_path, include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(os.fspath(STATIC_DIRPATH / "images" / "favicon.ico"))


# https://fastapi.tiangolo.com/async/#in-a-hurry
@plastered_web_router.get("/")
async def root_endpoint(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request=request,
        name="index.html",
        context={"plastered_version": request.state.lifespan_singleton.project_version},
    )


# /config
@plastered_web_router.get(Endpoint.CONFIG_PAGE.value.rel_path)
async def show_config_endpoint(request: Request) -> HTMLResponse:
    _LOGGER.debug(f"/config endpoint called at {datetime.now().timestamp()}")
    return TEMPLATES.TemplateResponse(request=request, name="config.html")


# /search_form<?entity=(album|track)>
@plastered_web_router.get(Endpoint.SEARCH_FORM.value.rel_path)
async def search_form_endpoint(request: Request, entity: EntityType | None = None) -> HTMLResponse:
    if entity is None:
        return TEMPLATES.TemplateResponse("manual_search.html", {"request": request})
    return TEMPLATES.TemplateResponse(
        request=request, name="fragments/search_modal.html", context={"entity": str(entity)}
    )


# /scrape_form
@plastered_web_router.get(Endpoint.SCRAPE_FORM.value.rel_path)
async def scrape_form_endpoint(request: Request) -> HTMLResponse:
    # TODO: have HTMX hit the /api/scrape endpoint following user setup
    return TEMPLATES.TemplateResponse(request=request, name="scrape_form.html")


# /run_history
@plastered_web_router.get(Endpoint.RUN_HISTORY_PAGE.value.rel_path)
async def runs_page(request: Request, search_id: int | None = None) -> HTMLResponse:
    # TODO: have HTMX hit the /api/run_history endpoint following user setup
    return TEMPLATES.TemplateResponse(request=request, name="run_history_page.html", context={"search_id": search_id})


# TODO [later]: add the html template and migrate logic of plastered.stats.PriorRunStats to here.
# @plastered_web_router.get(Endpoint.STATS_PAGE.value.rel_path)
# async def scraper_stats_page(request: Request) -> HTMLResponse:
#     return TEMPLATES.TemplateResponse(request=request, name="scraper_stats_page.html", context={})


@plastered_web_router.get(Endpoint.USER_DETAILS_PAGE.value.rel_path)
async def user_details_page(request: Request) -> HTMLResponse:
    red_user_details = request.state.lifespan_singleton.red_user_details
    return TEMPLATES.TemplateResponse(
        request=request,
        name="user_details.html",
        context={"user_id": red_user_details.user_id, "available_fl_tokens": red_user_details.available_fl_tokens},
    )


# /result_modal?<final-state-specific query parameters created by HTMX>
@plastered_web_router.get(Endpoint.RESULT_MODAL.value.rel_path)
async def result_modal(request: Request) -> HTMLResponse:
    _LOGGER.debug(f"endpoint /result_modal called with params: {request.query_params}")
    return TEMPLATES.TemplateResponse(
        request=request, name="fragments/result_modal.html", context={"params": request.query_params}
    )
