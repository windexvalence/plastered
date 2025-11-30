from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Final, NamedTuple
from urllib.parse import urlencode

from fastapi.templating import Jinja2Templates

API_ROUTES_PREFIX: Final[str] = "/api"
STATIC_ROUTES_PREFIX: Final[str] = "/static"
WEBSERVER_ROUTES_PREFIX: Final[str] = "/"
TEST_MODE: Final[bool] = os.getenv("PYTEST_VERSION") is not None


class RoutePath(NamedTuple):
    """
    Class for describing a particular FastAPI endpoint in a way that it may be referenced by
    both the internal FastAPI decorators and by absolute endpoint paths consistently.

    :param: rel_path (str):  The relative endpoint path, without the fastapi_prefix.
        This is what is passed to the fastapi decorators.
    :param: api_prefix (str): The FastAPI app prefix which the endpoint lives under.
    """

    rel_path: str
    api_prefix: str

    @property
    def full_path(self) -> str:  # pragma: no cover
        """The full endpoint path, including the fastapi_prefix."""
        return os.path.join(self.api_prefix, self.rel_path.removeprefix("/"))


class Endpoint(Enum):
    ### Main API endpoints below ###
    # /api/healthcheck
    HEALTHCHECK = RoutePath(rel_path="/healthcheck", api_prefix=API_ROUTES_PREFIX)
    # /api/config
    CONFIG = RoutePath(rel_path="/config", api_prefix=API_ROUTES_PREFIX)
    # /api/submit_search
    SUBMIT_SEARCH_FORM = RoutePath(rel_path="/submit_search_form", api_prefix=API_ROUTES_PREFIX)
    # /api/scrape
    SCRAPE = RoutePath(rel_path="/scrape", api_prefix=API_ROUTES_PREFIX)
    # /api/inspect_run
    INSPECT_RUN = RoutePath(rel_path="/inspect_run", api_prefix=API_ROUTES_PREFIX)
    # /api/run_history
    RUN_HISTORY = RoutePath(rel_path="/run_history", api_prefix=API_ROUTES_PREFIX)
    ### Web UI endpoints below ###
    # /favicon.ico
    FAVICON = RoutePath(rel_path="/favicon.ico", api_prefix=WEBSERVER_ROUTES_PREFIX)
    # /
    ROOT_PAGE = RoutePath(rel_path="/", api_prefix=WEBSERVER_ROUTES_PREFIX)
    # /config
    CONFIG_PAGE = RoutePath(rel_path="/config", api_prefix=WEBSERVER_ROUTES_PREFIX)
    # /search_form
    SEARCH_FORM = RoutePath(rel_path="/search_form", api_prefix=WEBSERVER_ROUTES_PREFIX)
    # /scrape_form
    SCRAPE_FORM = RoutePath(rel_path="/scrape_form", api_prefix=WEBSERVER_ROUTES_PREFIX)
    # /run_history
    RUN_HISTORY_PAGE = RoutePath(rel_path="/run_history", api_prefix=WEBSERVER_ROUTES_PREFIX)
    # /user_details
    USER_DETAILS_PAGE = RoutePath(rel_path="/user_details", api_prefix=WEBSERVER_ROUTES_PREFIX)
    # /result_modal
    RESULT_MODAL = RoutePath(rel_path="/result_modal", api_prefix=WEBSERVER_ROUTES_PREFIX)


_API_DIRPATH: Final[Path] = Path(os.path.join(os.environ["APP_DIR"], "plastered", "api"))
TEMPLATES_DIRPATH: Final[Path] = _API_DIRPATH / "templates"
STATIC_DIRPATH: Final[Path] = _API_DIRPATH / "static"
WEB_DATE_FMT: Final[str] = "%Y/%m/%d, %H:%M:%S"

TEMPLATES: Final[Jinja2Templates] = Jinja2Templates(directory=TEMPLATES_DIRPATH)
TEMPLATES.env.filters["dict_to_query_params"] = urlencode  # _dict_to_query_params

SUB_CONF_NAMES: Final[tuple[str, ...]] = ("format_preferences", "search", "snatches")
