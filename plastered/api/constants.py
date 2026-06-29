from __future__ import annotations

import os
from datetime import datetime
from enum import StrEnum, unique
from pathlib import Path
from typing import Final
from urllib.parse import urlencode

from fastapi.templating import Jinja2Templates

# User-facing labels for a run's terminal status, used by the run-history accordion summary line.
_STATUS_DISPLAY_LABELS: Final[dict[str, str]] = {
    "grabbed": "snatched",
    "matched": "found",
    "skipped": "skipped",
    "failed": "failed",
    "in_progress": "in progress",
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


@unique
class RouterPrefix(StrEnum):
    API = "/api"


_API_DIRPATH: Final[Path] = Path(os.path.join(os.environ["APP_DIR"], "plastered", "api"))
_TEMPLATES_DIRPATH: Final[Path] = _API_DIRPATH / "templates"

STATIC_DIRPATH: Final[Path] = _API_DIRPATH / "static"
TEMPLATES: Final[Jinja2Templates] = Jinja2Templates(directory=_TEMPLATES_DIRPATH)
TEMPLATES.env.filters["dict_to_query_params"] = urlencode
TEMPLATES.env.filters["format_timestamp"] = _format_timestamp
TEMPLATES.env.filters["status_label"] = _status_label
SUB_CONF_NAMES: Final[tuple[str, ...]] = ("format_preferences", "search", "snatches")
