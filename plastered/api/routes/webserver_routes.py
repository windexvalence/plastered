import logging
import os
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse

from plastered.actions.api_actions import adhoc_result_action, adhoc_snatch_action
from plastered.api.adhoc_helpers import build_adhoc_request_from_form, schedule_adhoc_search
from plastered.api.constants import STATIC_DIRPATH, TEMPLATES
from plastered.api.fastapi_dependencies import SessionDep
from plastered.models.types import RedReleaseType

_LOGGER = logging.getLogger(__name__)
plastered_web_router = APIRouter(prefix="")


@plastered_web_router.get("/favicon.ico", include_in_schema=False)
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
@plastered_web_router.get("/config")
async def show_config_endpoint(request: Request) -> HTMLResponse:
    _LOGGER.debug(f"/config endpoint called at {datetime.now().timestamp()}")
    return TEMPLATES.TemplateResponse(request=request, name="config.html")


# /adhoc  (the dedicated ad-hoc release search page)
@plastered_web_router.get("/adhoc")
async def adhoc_search_page(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request=request, name="adhoc_search.html", context={"release_types": list(RedReleaseType)}
    )


# POST /adhoc_search  (HTMX form submission -> schedules the search and returns the polling result fragment)
@plastered_web_router.post("/adhoc_search")
async def adhoc_search_submit(
    session: SessionDep,
    background_tasks: BackgroundTasks,
    request: Request,
    artist: Annotated[str, Form()],
    release: Annotated[str | None, Form()] = None,
    track: Annotated[str | None, Form()] = None,
    mbid: Annotated[str | None, Form()] = None,
    release_type: Annotated[str | None, Form()] = None,
    release_year: Annotated[str | None, Form()] = None,
    record_label: Annotated[str | None, Form()] = None,
    catalog_number: Annotated[str | None, Form()] = None,
    max_size_gb: Annotated[str | None, Form()] = None,
    snatch: Annotated[bool, Form()] = False,
) -> HTMLResponse:
    adhoc_request = build_adhoc_request_from_form(
        artist=artist,
        release=release,
        track=track,
        mbid=mbid,
        release_type=release_type,
        release_year=release_year,
        record_label=record_label,
        catalog_number=catalog_number,
        snatch=snatch,
        max_size_gb=max_size_gb,
    )
    search_id = schedule_adhoc_search(
        session=session,
        background_tasks=background_tasks,
        release_searcher=request.state.lifespan_singleton.release_searcher,
        req=adhoc_request,
    )
    return TEMPLATES.TemplateResponse(
        request=request, name="fragments/adhoc_result_fragment.html", context={"search_id": search_id, "result": None}
    )


# GET /adhoc_result?search_id=<int>  (HTMX polling fragment; re-renders until the search completes)
@plastered_web_router.get("/adhoc_result")
async def adhoc_result_fragment(session: SessionDep, request: Request, search_id: int) -> HTMLResponse:
    result = adhoc_result_action(search_id=search_id, session=session)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No ad-hoc search record matching search_id={search_id}."
        )
    return TEMPLATES.TemplateResponse(
        request=request, name="fragments/adhoc_result_fragment.html", context={"search_id": search_id, "result": result}
    )


# POST /adhoc_snatch  (HTMX per-result "Download" button -> snatch the already-matched release, return the result fragment)
@plastered_web_router.post("/adhoc_snatch")
async def adhoc_snatch_submit(session: SessionDep, request: Request, search_id: Annotated[int, Form()]) -> HTMLResponse:
    result = adhoc_snatch_action(
        release_searcher=request.state.lifespan_singleton.release_searcher, search_id=search_id, session=session
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No ad-hoc search record matching search_id={search_id}."
        )
    return TEMPLATES.TemplateResponse(
        request=request, name="fragments/adhoc_result_fragment.html", context={"search_id": search_id, "result": result}
    )


# /scrape_form
@plastered_web_router.get("/scrape_form")
async def scrape_form_endpoint(request: Request) -> HTMLResponse:
    # TODO: have HTMX hit the /api/scrape endpoint following user setup
    return TEMPLATES.TemplateResponse(request=request, name="scrape_form.html")


# /run_history
@plastered_web_router.get("/run_history")
async def runs_page(request: Request, search_id: int | None = None) -> HTMLResponse:
    # TODO: have HTMX hit the /api/run_history endpoint following user setup
    return TEMPLATES.TemplateResponse(request=request, name="run_history_page.html", context={"search_id": search_id})


@plastered_web_router.get("/user_details")
async def user_details_page(request: Request) -> HTMLResponse:
    red_user_details = request.state.lifespan_singleton.red_user_details
    return TEMPLATES.TemplateResponse(
        request=request,
        name="user_details.html",
        context={"user_id": red_user_details.user_id, "available_fl_tokens": red_user_details.available_fl_tokens},
    )


# /result_modal?<final-state-specific query parameters created by HTMX>
@plastered_web_router.get("/result_modal")
async def result_modal(request: Request) -> HTMLResponse:
    _LOGGER.debug(f"endpoint /result_modal called with params: {request.query_params}")
    return TEMPLATES.TemplateResponse(
        request=request, name="fragments/result_modal.html", context={"params": request.query_params}
    )
