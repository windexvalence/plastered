import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Final

import uvicorn
from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from plastered.actions import scrape_action, show_config_action
from plastered.actions.api_actions import inspect_run_action, manual_search_action, run_history_action
from plastered.config.app_settings import get_app_settings
from plastered.config.field_validators import CLIOverrideSetting
from plastered.db.db_models import SearchRun
from plastered.db.db_utils import db_startup, get_session
from plastered.models.types import EntityType
from plastered.version import get_project_version

_LOGGER = logging.getLogger(__name__)
# TODO (later): consolidate this to a single constant for both CLI and server to reference.
_VALID_REC_TYPES: Final[tuple[str, ...]] = tuple(["album", "track", "all"])
_TEMPLATES_DIRPATH: Final[Path] = Path(os.path.join(os.environ["APP_DIR"], "plastered", "api", "templates"))
templates = Jinja2Templates(directory=_TEMPLATES_DIRPATH)
_STATE: dict[str, Any] = {}


# Set up some application state stuff
@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    # Startup events: Initialize stuff
    _STATE["app_settings"] = get_app_settings()
    _STATE["config_filepath"] = _STATE["app_settings"].src_yaml_filepath
    _STATE["app_version"] = get_project_version()
    db_startup()
    yield
    # Shutdown events: Clean up stuff
    _STATE.clear()


# https://fastapi.tiangolo.com/tutorial/sql-databases/#create-models
SessionDep = Annotated[Session, Depends(get_session)]
fastapi_app = FastAPI(lifespan=_app_lifespan)


# https://fastapi.tiangolo.com/async/#in-a-hurry
@fastapi_app.get("/")
def root_endpoint() -> JSONResponse:
    return JSONResponse(content={"message": f"Plastered {_STATE['app_version']}"})


# /show_config
@fastapi_app.get("/show_config")
def show_config_endpoint() -> JSONResponse:
    return JSONResponse(content=show_config_action(app_settings=_STATE["app_settings"]))


@fastapi_app.get("/search_form")
def search_form_endpoint(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("manual_search.html.template", {"request": request})


@fastapi_app.post("/submit_album_search_form")
async def submit_album_search_form_endpoint(
    session: SessionDep, album: Annotated[str, Form()], artist: Annotated[str, Form()], mbid: str | None = Form(None)
) -> JSONResponse:
    manual_run_json_data = await manual_search_action(
        session=session,
        app_settings=_STATE["app_settings"],
        search_run=SearchRun(
            is_manual=True,
            artist=artist,
            entity=album,
            submit_timestamp=int(datetime.now().timestamp()),
            entity_type=EntityType.ALBUM,
        ),
        mbid=mbid,
    )
    return JSONResponse(content=manual_run_json_data, status_code=200)


@fastapi_app.post("/submit_track_search_form")
async def submit_track_search_form_endpoint(
    session: SessionDep, track: Annotated[str, Form()], artist: Annotated[str, Form()], mbid: str | None = Form(None)
) -> JSONResponse:
    return JSONResponse(content={"track": track, "artist": artist, "mbid": mbid if mbid else "n/a"}, status_code=200)


# /scrape?snatch=<false|true>&rec_type=<album|track|all>
@fastapi_app.post("/scrape")
def scrape_endpoint(snatch: bool = False, rec_type: str = "all") -> RedirectResponse:
    if rec_type not in _VALID_REC_TYPES:  # pragma: no cover
        msg = f"Invalid rec_type value '{rec_type}'. Must be one of {_VALID_REC_TYPES}"
        _LOGGER.warning(msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    target_entities = [et.value for et in EntityType] if rec_type == "all" else [rec_type]
    app_settings = get_app_settings(
        _STATE["config_filepath"],
        cli_overrides={
            CLIOverrideSetting.SNATCH_ENABLED.name: snatch,
            CLIOverrideSetting.REC_TYPES.name: target_entities,
        },
    )
    scrape_action(app_settings=app_settings)
    # 303 status code required to redirect from this endpoint (post) to the other endpoint (get)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


# /run_history?since_timestamp=<unix timestamp int>
@fastapi_app.get("/run_history")
def run_history_endpoint(session: SessionDep, since_timestamp: int | None = None) -> list[SearchRun]:
    if not since_timestamp:  # pragma: no cover
        # Default to the past 6 months if since is not provided
        since_timestamp = int((datetime.now(tz=UTC) - timedelta(days=180)).timestamp())
    return run_history_action(since_timestamp=since_timestamp, session=session)


# /inspect_run?run_id=<int>
@fastapi_app.get("/inspect_run")
def inspect_run_endpoint(session: SessionDep, run_id: int) -> JSONResponse:
    if matched_record := inspect_run_action(run_id=run_id, session=session):
        return JSONResponse(content=matched_record.model_dump(), status_code=status.HTTP_200_OK)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No records matching run_id={run_id} found.")


if __name__ == "__main__":
    app_settings = get_app_settings()
    uvicorn.run(
        "plastered.api.server:fastapi_app", host=app_settings.server.host, port=app_settings.server.port, reload=True
    )
