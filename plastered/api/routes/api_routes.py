import logging
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from plastered.actions import scrape_action, show_config_action
from plastered.actions.api_actions import (
    adhoc_result_action,
    adhoc_snatch_action,
    inspect_run_action,
    run_history_action,
)
from plastered.api.adhoc_helpers import schedule_adhoc_search
from plastered.api.api_models import (
    AdhocSearchRequest,
    AdhocSearchResult,
    AdhocSearchSubmittedResponse,
    RunHistoryListResponse,
)
from plastered.api.constants import SUB_CONF_NAMES, TEMPLATES, RouterPrefix
from plastered.api.fastapi_dependencies import SessionDep
from plastered.db.db_models import Status
from plastered.models import EntityType

_LOGGER = logging.getLogger(__name__)
plastered_api_router = APIRouter(prefix=str(RouterPrefix.API))


# /api/healthcheck
@plastered_api_router.get("/healthcheck")
async def healthcheck_endpoint(request: Request) -> JSONResponse:
    return JSONResponse(content={"version": request.state.lifespan_singleton.project_version}, status_code=200)


# /api/config?sub_conf=<format_preferences|search|snatch>
@plastered_api_router.get("/config", response_model=None)
async def show_config_endpoint(request: Request, sub_conf: str | None = None) -> JSONResponse | HTMLResponse:
    _LOGGER.debug(f"/api/config endpoint called at {datetime.now(tz=UTC).timestamp()}")
    conf_dict = show_config_action(app_settings=request.state.lifespan_singleton.app_settings)
    _LOGGER.debug(f"/api/config endpoint acquired conf_dict of size {len(conf_dict)}.")
    if request.headers.get("HX-Request") == "true":
        _LOGGER.debug("/api/config endpoint detected request from HTMX.")
        if sub_conf:
            if sub_conf not in SUB_CONF_NAMES:
                raise HTTPException(
                    status_code=404, detail=f"Invalid sub_conf '{sub_conf}'. Expected one of {SUB_CONF_NAMES}"
                )
            return TEMPLATES.TemplateResponse(
                request=request,
                name="fragments/sub_conf_table_fragment.html",
                context={
                    "conf": conf_dict["red"][sub_conf],
                    "config_section_name": sub_conf,
                    "html_formatted_section_name": sub_conf.replace("_", " ").capitalize(),
                },
            )
        conf_items = sorted(conf_dict.items(), key=lambda x: x[0])
        return TEMPLATES.TemplateResponse(
            request=request,
            name="fragments/config_fragment.html",
            context={"conf_items": conf_items, "sub_conf_names": SUB_CONF_NAMES},
        )
    return JSONResponse(content=conf_dict)


# /api/adhoc_search  (JSON REST entry point for the ad-hoc release search flow)
@plastered_api_router.post("/adhoc_search", status_code=status.HTTP_202_ACCEPTED)
async def adhoc_search_endpoint(
    session: SessionDep, background_tasks: BackgroundTasks, request: Request, adhoc_request: AdhocSearchRequest
) -> AdhocSearchSubmittedResponse:
    """
    Accepts an ad-hoc release search request (artist + one of release/track, all other fields optional, plus optional
    per-request config overrides), kicks the search off in the background, and returns the new search id. Poll
    `/api/adhoc_result?search_id=<id>` for the matched release(s) and any snatch information.
    """
    search_id = schedule_adhoc_search(
        session=session,
        background_tasks=background_tasks,
        release_searcher=request.state.lifespan_singleton.release_searcher,
        req=adhoc_request,
    )
    return AdhocSearchSubmittedResponse(
        search_id=search_id, status=Status.IN_PROGRESS, result_url=f"/api/adhoc_result?search_id={search_id}"
    )


# /api/adhoc_result?search_id=<int>
@plastered_api_router.get("/adhoc_result")
async def adhoc_result_endpoint(session: SessionDep, search_id: int) -> AdhocSearchResult:
    """Returns the matched release(s) + snatch information for an ad-hoc search once it has completed."""
    if (result := adhoc_result_action(search_id=search_id, session=session)) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No ad-hoc search record matching search_id={search_id}."
        )
    return result


# /api/adhoc_snatch?search_id=<int>  (download an already-matched release from a search-only run)
@plastered_api_router.post("/adhoc_snatch")
async def adhoc_snatch_endpoint(session: SessionDep, request: Request, search_id: int) -> AdhocSearchResult:
    """Snatches the release previously matched (but not downloaded) for an ad-hoc search, and returns the updated result."""
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
    return result


# /api/scrape?snatch=<false|true>&rec_type=<album|track|None>
@plastered_api_router.post("/scrape")
async def scrape_endpoint(
    request: Request, session: SessionDep, snatch: bool = False, rec_type: EntityType | None = None
) -> RedirectResponse:
    scrape_action(
        app_settings=request.state.lifespan_singleton.app_settings,
        rec_types_to_scrape_override=[rec_type] if rec_type is not None else [et for et in EntityType],
        snatch_override=snatch,
    )
    # 303 status code required to redirect from this endpoint (post) to the other endpoint (get)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


# /api/inspect_run?run_id=<int>
@plastered_api_router.get("/inspect_run")
async def inspect_run_endpoint(session: SessionDep, run_id: int) -> JSONResponse:
    if matched_record := inspect_run_action(run_id=run_id, session=session):
        return JSONResponse(content=matched_record.model_dump(), status_code=status.HTTP_200_OK)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No records matching run_id={run_id} found.")


# /api/run_history?since_timestamp=<unix timestamp int>&final_state=<success|skipped|failed>&submitted_search_id=<int>
@plastered_api_router.get("/run_history")
async def run_history_endpoint(
    session: SessionDep,
    since_timestamp: int | None = None,
    final_state: Status | None = None,
    search_id: int | None = None,
) -> RunHistoryListResponse:
    return run_history_action(
        since_timestamp=since_timestamp, session=session, final_state=final_state, search_id=search_id
    )
