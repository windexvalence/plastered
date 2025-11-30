from collections.abc import Generator
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from plastered.config.app_settings import AppSettings, get_app_settings
from plastered.db.db_models import ENGINE
from plastered.models.red_models import RedUserDetails
from plastered.utils.httpx_utils.red_client import RedAPIClient
from plastered.version import get_project_version


class _DependencySingletons:  # pragma: no cover
    """
    Pre-define various dependency objects that should live for the duration of the app so we don't recreate it on
    each API call that uses these subsequent dependencies.

    NOTE: when adding a new FastAPI dep singleton here, make sure to also add it to the `mock_DependencySingletons_inst` pytest fixture
    """

    _app_settings_instance: AppSettings | None = None
    _red_user_details_instance: RedUserDetails | None = None
    _project_version_instance: str | None = None

    @classmethod
    def get_app_settings_instance(cls) -> AppSettings:
        if cls._app_settings_instance is None:
            cls._app_settings_instance = get_app_settings()
        return cls._app_settings_instance

    @classmethod
    def get_red_user_details_instance(cls) -> RedUserDetails:
        if cls._red_user_details_instance is None:
            cls._red_user_details_instance = cls._init_red_user_details(app_settings=cls.get_app_settings_instance())
        return cls._red_user_details_instance

    @classmethod
    def get_project_version_instance(cls) -> str:
        if cls._project_version_instance is None:
            cls._project_version_instance = get_project_version()
        return cls._project_version_instance

    @staticmethod
    def _init_red_user_details(app_settings: AppSettings) -> RedUserDetails:
        """
        Internal method for creating a single, re-usable `RedUserDetails` instance for as a FastAPI dependency.
        NOTE: This function should not be used directly for the FastAPI dependency definition, but called at the top-level of this module
        and the result assigned to the single `_red_user_details_instance` variable below.
        """
        red_api_client = RedAPIClient(app_settings=app_settings)
        return red_api_client.create_red_user_details()


AppSettingsDep = Annotated[AppSettings, Depends(_DependencySingletons.get_app_settings_instance)]
PlasteredVersionDep = Annotated[str, Depends(_DependencySingletons.get_project_version_instance)]
RedUserDetailsDep = Annotated[RedUserDetails, Depends(_DependencySingletons.get_red_user_details_instance)]


def _get_config_filepath(app_settings: AppSettingsDep) -> Path:
    return app_settings.src_yaml_filepath


def _get_session() -> Generator[Session, None, None]:
    with Session(ENGINE) as session:
        yield session


ConfigFilepathDep = Annotated[Path, Depends(_get_config_filepath)]
SessionDep = Annotated[Session, Depends(_get_session)]
