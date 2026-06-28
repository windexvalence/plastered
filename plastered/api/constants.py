from __future__ import annotations

import os
from enum import StrEnum, unique
from pathlib import Path
from typing import Final
from urllib.parse import urlencode

from fastapi.templating import Jinja2Templates


@unique
class RouterPrefix(StrEnum):
    API = "/api"


_API_DIRPATH: Final[Path] = Path(os.path.join(os.environ["APP_DIR"], "plastered", "api"))
_TEMPLATES_DIRPATH: Final[Path] = _API_DIRPATH / "templates"

STATIC_DIRPATH: Final[Path] = _API_DIRPATH / "static"
TEMPLATES: Final[Jinja2Templates] = Jinja2Templates(directory=_TEMPLATES_DIRPATH)
TEMPLATES.env.filters["dict_to_query_params"] = urlencode
SUB_CONF_NAMES: Final[tuple[str, ...]] = ("format_preferences", "search", "snatches")
