import os
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlencode

from fastapi.templating import Jinja2Templates

_API_DIRPATH: Final[Path] = Path(os.path.join(os.environ["APP_DIR"], "plastered", "api"))
TEMPLATES_DIRPATH: Final[Path] = _API_DIRPATH / "templates"
STATIC_DIRPATH: Final[Path] = _API_DIRPATH / "static"
WEB_DATE_FMT: Final[str] = "%Y/%m/%d, %H:%M:%S"


def _dict_to_query_params(d: dict[str, Any]) -> str:
    """
    Custom Jinja filter to convert a dictionary to a query param fragment of the form:
    <key_1>=<val_1>&<key_2>=<val_2>...
    """
    return urlencode(d)


TEMPLATES: Final[Jinja2Templates] = Jinja2Templates(directory=TEMPLATES_DIRPATH)
TEMPLATES.env.filters["dict_to_query_params"] = _dict_to_query_params

SUB_CONF_NAMES: Final[tuple[str, ...]] = ("format_preferences", "search", "snatches")
