from __future__ import annotations

import importlib.resources
from datetime import datetime
from enum import StrEnum, unique
from pathlib import Path
from typing import TYPE_CHECKING, Final
from urllib.parse import urlencode

from fastapi.templating import Jinja2Templates

if TYPE_CHECKING:
    from fastapi import Request

# User-facing labels for a run's terminal status, used by the run-history accordion summary line.
_STATUS_DISPLAY_LABELS: Final[dict[str, str]] = {
    "grabbed": "snatched",
    "matched": "found",
    "skipped": "skipped",
    "failed": "failed",
    "in_progress": "in progress",
    "completed": "completed",
}


def _format_timestamp(timestamp: int | None) -> str:
    """Jinja filter: render a unix timestamp as a local 'YYYY-MM-DD HH:MM:SS' string."""
    if timestamp is None:
        return "—"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _status_label(status: object) -> str:
    """Jinja filter: render a run `Status` as a friendly label (e.g. grabbed -> snatched, matched -> found)."""
    if status is None:
        return "unknown"
    return _STATUS_DISPLAY_LABELS.get(str(status), str(status))


def _auth_template_context(request: Request) -> dict[str, bool]:
    """Template context processor: exposes `auth_enabled` to every page so shared chrome (e.g. the nav-bar logout
    control in `base_template.html`) can render conditionally on `server.auth.enable_login_protection`."""
    auth_config = request.app.state.lifespan_singleton.app_settings.server.auth
    return {"auth_enabled": auth_config.enable_login_protection}


@unique
class RouterPrefix(StrEnum):
    API = "/api"


# Resolved from the package itself (not APP_DIR), so the api assets ship inside any packaged form of the
# app (e.g. the PEX image). Assumes the package is materialized on disk (true for a source checkout, a
# venv install, and a `--venv`-mode PEX), since StaticFiles/Jinja2Templates need real directories.
_API_DIRPATH: Final[Path] = Path(str(importlib.resources.files("plastered.api")))
_TEMPLATES_DIRPATH: Final[Path] = _API_DIRPATH / "templates"

STATIC_DIRPATH: Final[Path] = _API_DIRPATH / "static"
TEMPLATES: Final[Jinja2Templates] = Jinja2Templates(
    directory=_TEMPLATES_DIRPATH, context_processors=[_auth_template_context]
)
TEMPLATES.env.filters["dict_to_query_params"] = urlencode
TEMPLATES.env.filters["format_timestamp"] = _format_timestamp
TEMPLATES.env.filters["status_label"] = _status_label
SUB_CONF_NAMES: Final[tuple[str, ...]] = ("format_preferences", "search", "snatches")
