"""
Collection of singleton resources spanning the full FastAPI lifespan.

These are NOT FastAPI dependencies, as those are scoped-per request. For more, see link below:
https://fastapi.tiangolo.com/advanced/events/
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from plastered.config.app_settings import get_app_settings
from plastered.utils.httpx_utils.red_client import RedAPIClient
from plastered.version import get_project_version


def get_lifespan_singleton() -> LifespanSingleton:
    """The only function that FastAPI logic should call to get the lifespan singleton"""
    return LifespanSingleton()


@dataclass(frozen=True)
class LifespanSingleton:
    """Wrapper singleton class for managing any singleton lifespan objects as attributes."""

    # app_settings: AppSettings
    # config_filepath: Path
    # red_api_client: RedAPIClient
    # red_user_details: RedUserDetails
    # project_version: str
    _instance: Self | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __post_init__(self):
        object.__setattr__(self, "app_settings", get_app_settings())
        object.__setattr__(self, "config_filepath", self.app_settings.src_yaml_filepath)
        object.__setattr__(self, "red_api_client", RedAPIClient(app_settings=self.app_settings))
        object.__setattr__(self, "red_user_details", self.red_api_client.create_red_user_details())
        object.__setattr__(self, "project_version", get_project_version())

    def shutdown(self):
        """Called at the end of the FastAPI app during the cleanup phase of the lifespan function."""
        self.red_api_client.close_client()
