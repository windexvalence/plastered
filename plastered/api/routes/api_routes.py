import logging
from datetime import UTC, datetime
from typing import Annotated, Final

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import ValidationError

from plastered.actions import scrape_action, show_config_action
from plastered.actions.api_actions import inspect_run_action, manual_search_action, run_history_action
from plastered.api.api_models import RunHistoryListResponse
from plastered.api.constants import API_ROUTES_PREFIX, SUB_CONF_NAMES, TEMPLATES, Endpoint
from plastered.api.fastapi_dependencies import SessionDep
from plastered.config.app_settings import get_app_settings
from plastered.config.field_validators import CLIOverrideSetting
from plastered.db.db_models import SearchRecord, Status
from plastered.db.db_utils import add_record
from plastered.models.types import EntityType

_LOGGER = logging.getLogger(__name__)
# TODO (later): consolidate this to a single constant for both CLI and server to reference.
_VALID_REC_TYPES: Final[tuple[str, ...]] = tuple(["album", "track", "all"])
plastered_api_router = APIRouter(prefix=API_ROUTES_PREFIX)


# /api/healthcheck
@plastered_api_router.get(Endpoint.HEALTHCHECK.value.rel_path)
async def healthcheck_endpoint(request: Request) -> JSONResponse:
    return JSONResponse(content={"version": request.state.lifespan_singleton.project_version}, status_code=200)


# /api/config?sub_conf=<format_preferences|search|snatch>
@plastered_api_router.get(Endpoint.CONFIG.value.rel_path, response_model=None)
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


# /api/submit_search
@plastered_api_router.post(Endpoint.SUBMIT_SEARCH_FORM.value.rel_path)
async def submit_search_form_endpoint(
    session: SessionDep,
    background_tasks: BackgroundTasks,
    request: Request,
    entity: Annotated[str, Form()],
    artist: Annotated[str, Form()],
    is_track: Annotated[bool, Form()],
    mbid: str | None = Form(None),  # noqa: FAST002
) -> RedirectResponse:
    model_inst = SearchRecord(
        is_manual=True,
        artist=artist,
        entity=entity,
        submit_timestamp=int(datetime.now(tz=UTC).timestamp()),
        entity_type=EntityType.TRACK if is_track else EntityType.ALBUM,
        status=Status.IN_PROGRESS,
    )
    try:
        db_initial_result = SearchRecord.model_validate(model_inst)
    except ValidationError as ex:  # pragma: no cover
        msg = f"Bad SearchRecord model provided. Failed validation with following errors: {ex.errors()}"
        _LOGGER.error(msg, exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from ex
    _LOGGER.debug(f"POST {Endpoint.SUBMIT_SEARCH_FORM.value.full_path} {entity=} {artist=} {is_track=} {mbid=}")
    add_record(session=session, model_inst=db_initial_result)
    if (search_id := db_initial_result.id) is None:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unable to create search record")
    background_tasks.add_task(
        func=manual_search_action,
        app_settings=request.state.lifespan_singleton.app_settings,
        red_user_details=request.state.lifespan_singleton.red_user_details,
        search_id=search_id,
        mbid=mbid,  # type: ignore[call-arg]
        **request.state.lifespan_singleton.get_all_client_kwargs(),
    )
    # 303 status code required to redirect from this endpoint (post) to the other endpoint (get)
    return RedirectResponse(
        url=f"{Endpoint.RUN_HISTORY_PAGE.value.full_path}?submitted_search_id={search_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# /api/scrape?snatch=<false|true>&rec_type=<album|track|all>
@plastered_api_router.post(Endpoint.SCRAPE.value.rel_path)
async def scrape_endpoint(
    request: Request, session: SessionDep, snatch: bool = False, rec_type: str = "all"
) -> RedirectResponse:
    if rec_type not in _VALID_REC_TYPES:  # pragma: no cover
        msg = f"Invalid rec_type value '{rec_type}'. Must be one of {_VALID_REC_TYPES}"
        _LOGGER.warning(msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    target_entities = [et.value for et in EntityType] if rec_type == "all" else [rec_type]
    app_settings = get_app_settings(
        request.state.lifespan_singleton.config_filepath,
        cli_overrides={
            CLIOverrideSetting.SNATCH_ENABLED.name: snatch,
            CLIOverrideSetting.REC_TYPES.name: target_entities,
        },
    )
    scrape_action(app_settings=app_settings)
    # 303 status code required to redirect from this endpoint (post) to the other endpoint (get)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


# /api/inspect_run?run_id=<int>
@plastered_api_router.get(Endpoint.INSPECT_RUN.value.rel_path)
async def inspect_run_endpoint(session: SessionDep, run_id: int) -> JSONResponse:
    if matched_record := inspect_run_action(run_id=run_id, session=session):
        return JSONResponse(content=matched_record.model_dump(), status_code=status.HTTP_200_OK)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No records matching run_id={run_id} found.")


# /api/run_history?since_timestamp=<unix timestamp int>&final_state=<success|skipped|failed>&submitted_search_id=<int>
@plastered_api_router.get(Endpoint.RUN_HISTORY.value.rel_path)
async def run_history_endpoint(
    session: SessionDep,
    since_timestamp: int | None = None,
    final_state: Status | None = None,
    search_id: int | None = None,
) -> RunHistoryListResponse:
    return run_history_action(
        since_timestamp=since_timestamp, session=session, final_state=final_state, search_id=search_id
    )
