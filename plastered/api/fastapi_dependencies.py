from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from plastered.config.app_settings import AppSettings, get_app_settings
from plastered.db.db_utils import get_session
from plastered.version import get_project_version

AppSettingsDep = Annotated[AppSettings, Depends(get_app_settings)]


def _get_config_filepath(app_settings: AppSettingsDep) -> Path:
    return app_settings.src_yaml_filepath


ConfigFilepathDep = Annotated[Path, Depends(_get_config_filepath)]
PlasteredVersionDep = Annotated[str, Depends(get_project_version)]
SessionDep = Annotated[Session, Depends(get_session)]
