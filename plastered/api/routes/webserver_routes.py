import logging
import os
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse
from starlette.concurrency import run_in_threadpool

from plastered.actions.api_actions import (
    adhoc_result_action,
    adhoc_snatch_action,
    get_latest_rec_download_batch,
    get_scraper_run_action,
    run_history_page_action,
    run_rec_download_batch_action,
    scraper_run_matched_rec_ids,
    scraper_run_recs_action,
)
from plastered.actions.common_actions import run_lfm_scraper
from plastered.api.adhoc_helpers import build_adhoc_request_from_form, schedule_adhoc_search
from plastered.api.constants import STATIC_DIRPATH, TEMPLATES
from plastered.api.fastapi_dependencies import SessionDep
from plastered.db.db_models import RecDownloadBatchStatus, Status
from plastered.db.db_utils import create_rec_download_batch, create_scraper_run
from plastered.models.types import EntityType, RedReleaseType

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
    # Run the snatch (which makes a throttled, busy-waiting RED request) off the event loop so it never blocks it.
    result = await run_in_threadpool(
        adhoc_snatch_action,
        release_searcher=request.state.lifespan_singleton.release_searcher,
        search_id=search_id,
        session=session,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No ad-hoc search record matching search_id={search_id}."
        )
    return TEMPLATES.TemplateResponse(
        request=request, name="fragments/adhoc_result_fragment.html", context={"search_id": search_id, "result": result}
    )


# /lfm_recommendations_scraper  (page: scraper controls + a status container)
@plastered_web_router.get("/lfm_recommendations_scraper")
async def lfm_scraper_page(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(request=request, name="lfm_scraper.html")


# POST /lfm_scraper_run  (start a scrape in the background, return the polling status fragment)
@plastered_web_router.post("/lfm_scraper_run")
async def lfm_scraper_run_submit(
    session: SessionDep,
    background_tasks: BackgroundTasks,
    request: Request,
    rec_type: Annotated[str | None, Form()] = None,
    snatch: Annotated[bool, Form()] = False,
) -> HTMLResponse:
    singleton = request.state.lifespan_singleton
    app_settings = singleton.app_settings
    rec_types_override = [EntityType(rec_type)] if rec_type in {member.value for member in EntityType} else None
    effective_rec_types = (
        [member.value for member in rec_types_override] if rec_types_override else app_settings.lfm.rec_types_to_scrape
    )
    run_id = create_scraper_run(
        snatch_enabled=snatch, rec_types=effective_rec_types, submit_timestamp=int(datetime.now(tz=UTC).timestamp())
    )
    background_tasks.add_task(
        func=run_lfm_scraper,
        app_settings=app_settings,
        release_searcher=singleton.release_searcher,
        run_id=run_id,
        rec_types_to_scrape_override=rec_types_override,
        snatch_enabled=snatch,
    )
    return TEMPLATES.TemplateResponse(
        request=request,
        name="fragments/lfm_scraper_status_fragment.html",
        context={"run": get_scraper_run_action(run_id=run_id, session=session)},
    )


# GET /lfm_scraper_status?run_id=<int>  (HTMX polling fragment for an in-flight scrape)
@plastered_web_router.get("/lfm_scraper_status")
async def lfm_scraper_status_fragment(session: SessionDep, request: Request, run_id: int) -> HTMLResponse:
    run = get_scraper_run_action(run_id=run_id, session=session)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No scraper run matching run_id={run_id}.")
    return TEMPLATES.TemplateResponse(
        request=request, name="fragments/lfm_scraper_status_fragment.html", context={"run": run}
    )


# /run_history  (page shell: filter/sort controls + a results container that loads the fragment below)
@plastered_web_router.get("/run_history")
async def runs_page(request: Request, search_id: int | None = None) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(request=request, name="run_history_page.html", context={"search_id": search_id})


# /run_history_list  (HTMX fragment: a single paginated page of run-history accordion rows)
@plastered_web_router.get("/run_history_list")
async def run_history_list_fragment(
    session: SessionDep,
    request: Request,
    page: int = 1,
    status: str | None = None,
    q: str | None = None,
    sort: str = "desc",
    search_id: int | None = None,
) -> HTMLResponse:
    status_filter = Status(status) if status in {member.value for member in Status} else None
    page_response = run_history_page_action(
        session=session,
        page=page,
        status_filter=status_filter,
        query=q or None,
        sort_desc=(sort != "asc"),
        search_id=search_id,
    )
    return TEMPLATES.TemplateResponse(
        request=request, name="fragments/run_history_list_fragment.html", context={"page": page_response}
    )


def _scraper_recs_response(request: Request, session: SessionDep, run_id: int) -> HTMLResponse:
    """Renders the scraper-run recs sub-fragment (recs table + download controls + batch progress)."""
    run_recs = scraper_run_recs_action(session=session, run_id=run_id)
    if run_recs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No scraper run matching run_id={run_id}.")
    run, recs, batch = run_recs
    return TEMPLATES.TemplateResponse(
        request=request,
        name="fragments/scraper_run_recs_fragment.html",
        context={"run": run, "recs": recs, "batch": batch},
    )


# GET /scraper_run_recs?run_id=<int>  (recs sub-fragment; also the HTMX poll target while a download batch runs)
@plastered_web_router.get("/scraper_run_recs")
async def scraper_run_recs_fragment(session: SessionDep, request: Request, run_id: int) -> HTMLResponse:
    return _scraper_recs_response(request=request, session=session, run_id=run_id)


# POST /scraper_run_snatch  (download selected/all matched recs of a downloads-disabled scraper run, in the background)
@plastered_web_router.post("/scraper_run_snatch")
async def scraper_run_snatch_submit(
    session: SessionDep,
    background_tasks: BackgroundTasks,
    request: Request,
    run_id: Annotated[int, Form()],
    search_ids: Annotated[list[int] | None, Form()] = None,
    download_all: Annotated[bool, Form()] = False,
) -> HTMLResponse:
    run = get_scraper_run_action(run_id=run_id, session=session)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No scraper run matching run_id={run_id}.")
    # Resolve the recs to download to this run's currently-matched (un-downloaded) recs, honoring the selection.
    matched_ids = scraper_run_matched_rec_ids(session=session, run=run)
    selected = matched_ids if download_all else [rec_id for rec_id in (search_ids or []) if rec_id in matched_ids]
    # Don't start a second batch while one is already running for this run; ignore empty/no-op requests.
    latest_batch = get_latest_rec_download_batch(session, run_id)
    already_running = latest_batch is not None and latest_batch.status == RecDownloadBatchStatus.IN_PROGRESS
    if selected and not already_running:
        batch_id = create_rec_download_batch(
            scraper_run_id=run_id, total=len(selected), submit_timestamp=int(datetime.now(tz=UTC).timestamp())
        )
        background_tasks.add_task(
            func=run_rec_download_batch_action,
            release_searcher=request.state.lifespan_singleton.release_searcher,
            batch_id=batch_id,
            search_ids=selected,
        )
    return _scraper_recs_response(request=request, session=session, run_id=run_id)


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
