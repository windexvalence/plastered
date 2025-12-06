"""
Collection of singleton resources spanning the full FastAPI lifespan.

These are NOT FastAPI dependencies, as those are scoped-per request. For more, see link below:
https://fastapi.tiangolo.com/advanced/events/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self

from plastered.config.app_settings import get_app_settings
from plastered.utils.httpx_utils.lfm_client import LFMAPIClient
from plastered.utils.httpx_utils.musicbrainz_client import MusicBrainzAPIClient
from plastered.utils.httpx_utils.red_client import RedAPIClient
from plastered.utils.httpx_utils.red_snatch_client import RedSnatchAPIClient
from plastered.version import get_project_version

if TYPE_CHECKING:
    from pathlib import Path

    from plastered.config.app_settings import AppSettings
    from plastered.models.red_models import RedUserDetails
    from plastered.utils.httpx_utils.base_client import ThrottledAPIBaseClient


def get_lifespan_singleton() -> LifespanSingleton:
    """The only function that FastAPI logic should call to get the lifespan singleton"""
    return LifespanSingleton()


@dataclass(frozen=True)
class LifespanSingleton:
    """Wrapper singleton class for managing any singleton lifespan objects as attributes."""

    app_settings: AppSettings = field(init=False)
    config_filepath: Path = field(init=False)
    red_api_client: RedAPIClient = field(init=False)
    red_user_details: RedUserDetails = field(init=False)
    red_snatch_client: RedSnatchAPIClient = field(init=False)
    lfm_client: LFMAPIClient = field(init=False)
    musicbrainz_client: MusicBrainzAPIClient = field(init=False)

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
        object.__setattr__(self, "red_snatch_client", RedSnatchAPIClient(app_settings=self.app_settings))
        object.__setattr__(self, "lfm_client", LFMAPIClient(app_settings=self.app_settings))
        object.__setattr__(self, "musicbrainz_client", MusicBrainzAPIClient(app_settings=self.app_settings))
        object.__setattr__(self, "project_version", get_project_version())

    def get_all_client_kwargs(self) -> dict[str, ThrottledAPIBaseClient]:  # pragma: no cover
        """Returns all the base client subclass instances as a kwarg-compatible dict."""
        return {
            "red_api_client": self.red_api_client,
            "red_snatch_client": self.red_snatch_client,
            "lfm_client": self.lfm_client,
            "musicbrainz_client": self.musicbrainz_client,
        }

    def shutdown(self):
        """Called at the end of the FastAPI app during the cleanup phase of the lifespan function."""
        self.red_api_client.close_client()
        self.red_snatch_client.close_client()
        self.lfm_client.close_client()
        self.musicbrainz_client.close_client()
