import json
import logging
from datetime import UTC, datetime, timedelta
from pprint import pformat
from typing import Annotated, Final

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from plastered.actions import scrape_action, show_config_action
from plastered.actions.api_actions import inspect_run_action, manual_search_action, run_history_action
from plastered.api.constants import SUB_CONF_NAMES, TEMPLATES, WEB_DATE_FMT
from plastered.api.fastapi_dependencies import AppSettingsDep, ConfigFilepathDep, PlasteredVersionDep, SessionDep
from plastered.config.app_settings import get_app_settings
from plastered.config.field_validators import CLIOverrideSetting
from plastered.db.db_models import Result, Status
from plastered.db.db_utils import query_rows_to_jinja_context_obj
from plastered.models.types import EntityType

_LOGGER = logging.getLogger(__name__)
# TODO (later): consolidate this to a single constant for both CLI and server to reference.
_VALID_REC_TYPES: Final[tuple[str, ...]] = tuple(["album", "track", "all"])

API_URL_PATH_PREFIX: Final[str] = "/api"
plastered_api_router = APIRouter(prefix=API_URL_PATH_PREFIX)


# /api/healthcheck
@plastered_api_router.get("/healthcheck")
async def healthcheck_endpoint(plastered_version: PlasteredVersionDep) -> JSONResponse:
    return JSONResponse(content={"version": plastered_version}, status_code=200)


# /api/config?sub_conf=<format_preferences|search|snatch>
@plastered_api_router.get("/config", response_model=None)
async def show_config_endpoint(
    app_settings: AppSettingsDep, request: Request, sub_conf: str | None = None
) -> JSONResponse | HTMLResponse:
    _LOGGER.debug(f"/api/config endpoint called at {datetime.now(tz=UTC).timestamp()}")
    conf_dict = show_config_action(app_settings=app_settings)
    _LOGGER.debug(f"/api/config endpoint acquired conf_dict of size {len(conf_dict)}.")
    if request.headers.get("HX-Request") == "true":
        _LOGGER.debug("/api/config endpoint detected request from HTMX.")
        json.loads(app_settings.model_dump_json())
        if sub_conf:
            if sub_conf not in SUB_CONF_NAMES:
                raise HTTPException(
                    status_code=404, detail=f"Invalid sub_conf '{sub_conf}'. Expected one of {SUB_CONF_NAMES}"
                )
            return TEMPLATES.TemplateResponse(
                name="fragments/sub_conf_table_fragment.html",
                request=request,
                context={
                    "conf": conf_dict["red"][sub_conf],
                    "config_section_name": sub_conf,
                    "html_formatted_section_name": sub_conf.replace("_", " ").capitalize(),
                },
            )
        conf_items = sorted(conf_dict.items(), key=lambda x: x[0])
        return TEMPLATES.TemplateResponse(
            name="fragments/config_fragment.html",
            request=request,
            context={"conf_items": conf_items, "sub_conf_names": SUB_CONF_NAMES},
        )
    return JSONResponse(content=conf_dict)


# /api/submit_search
@plastered_api_router.post("/submit_search_form")
async def submit_search_form_endpoint(
    session: SessionDep,
    app_settings: AppSettingsDep,
    background_tasks: BackgroundTasks,
    request: Request,
    entity: Annotated[str, Form()],
    artist: Annotated[str, Form()],
    is_track: bool = False,
    mbid: str | None = Form(None),  # noqa: FAST002
) -> JSONResponse:
    _LOGGER.debug(f"POST /api/submit_album_search_form {entity=} {artist=} {is_track=} {mbid=}")
    background_tasks.add_task(  # type: ignore[call-arg]
        func=manual_search_action,
        session=session,
        app_settings=app_settings,
        search_result_record=Result(
            is_manual=True,
            artist=artist,
            entity=entity,
            submit_timestamp=int(datetime.now(tz=UTC).timestamp()),
            entity_type=EntityType.TRACK if is_track else EntityType.ALBUM,
        ),
        mbid=mbid,
    )
    return JSONResponse(content={}, status_code=200)


# /api/scrape?snatch=<false|true>&rec_type=<album|track|all>
@plastered_api_router.post("/scrape")
def scrape_endpoint(
    session: SessionDep, config_filepath: ConfigFilepathDep, snatch: bool = False, rec_type: str = "all"
) -> RedirectResponse:
    if rec_type not in _VALID_REC_TYPES:  # pragma: no cover
        msg = f"Invalid rec_type value '{rec_type}'. Must be one of {_VALID_REC_TYPES}"
        _LOGGER.warning(msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    target_entities = [et.value for et in EntityType] if rec_type == "all" else [rec_type]
    app_settings = get_app_settings(
        config_filepath,
        cli_overrides={
            CLIOverrideSetting.SNATCH_ENABLED.name: snatch,
            CLIOverrideSetting.REC_TYPES.name: target_entities,
        },
    )
    scrape_action(app_settings=app_settings)
    # 303 status code required to redirect from this endpoint (post) to the other endpoint (get)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


# /api/inspect_run?run_id=<int>
@plastered_api_router.get("/inspect_run")
def inspect_run_endpoint(session: SessionDep, run_id: int) -> JSONResponse:
    if matched_record := inspect_run_action(run_id=run_id, session=session):
        return JSONResponse(content=matched_record.model_dump(), status_code=status.HTTP_200_OK)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No records matching run_id={run_id} found.")


# /api/run_history?since_timestamp=<unix timestamp int>&final_state=<success|skipped|failed>
@plastered_api_router.get("/run_history", response_model=None)
def run_history_endpoint(
    session: SessionDep, request: Request, since_timestamp: int | None = None, final_state: Status | None = None
) -> JSONResponse | HTMLResponse:
    since_timestamp = since_timestamp if since_timestamp else _default_since_ts()
    records = run_history_action(since_timestamp=since_timestamp, session=session, final_state=final_state)
    if request.headers.get("HX-Request") == "true":
        _LOGGER.debug("/api/run_history Request received from HTMX. Will return as HTML fragment.")
        try:
            return TEMPLATES.TemplateResponse(
                name="fragments/run_history_list_fragment.html",
                request=request,
                context={
                    "records": query_rows_to_jinja_context_obj(records),
                    "sr_ids_to_submit_dates": {
                        sr.Result.id: datetime.fromtimestamp(sr.Result.submit_timestamp).strftime(WEB_DATE_FMT)
                        for sr in records
                    },
                },
            )
        except AttributeError as ex:  # pragma: no cover
            _LOGGER.error(f"AttributeError: {pformat(records)}", exc_info=True)
            raise ex
    return JSONResponse(content=records, status_code=200)


def _default_since_ts() -> int:  # pragma: no cover
    """Returns the default timestamp 6 months ago for date-ranged default queries."""
    return int((datetime.now(tz=UTC) - timedelta(days=180)).timestamp())
