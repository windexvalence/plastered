from typing import Generator
from unittest.mock import MagicMock, PropertyMock, patch

from fastapi.testclient import TestClient
import pytest

from plastered.api.lifespan_resources import LifespanSingleton
from plastered.api.webserver import fastapi_app
from plastered.config.app_settings import AppSettings
from plastered.models.red_models import RedUserDetails
from plastered.utils.httpx_utils.red_client import RedAPIClient
from plastered.version import get_project_version


@pytest.fixture(scope="session", autouse=True)
def mock_LifespanSingleton_inst(
    request: pytest.FixtureRequest, valid_app_settings_sesh_scoped: AppSettings, mock_red_user_details: RedUserDetails
) -> Generator[LifespanSingleton, None, None]:
    if "no_autouse_mock_lifespan_singleton_inst" in request.keywords:
        return

    from fastapi import BackgroundTasks

    with patch.object(RedAPIClient, "create_red_user_details", return_value=mock_red_user_details):
        singleton_inst = MagicMock(spec=LifespanSingleton)
        type(singleton_inst).app_settings = PropertyMock(return_value=valid_app_settings_sesh_scoped)
        app_settings_src_filepath = valid_app_settings_sesh_scoped.src_yaml_filepath
        type(singleton_inst).config_filepath = PropertyMock(return_value=app_settings_src_filepath)
        type(singleton_inst).red_api_client = PropertyMock(return_value=MagicMock(spec=RedAPIClient))
        type(singleton_inst).red_user_details = PropertyMock(return_value=mock_red_user_details)
        type(singleton_inst).project_version = PropertyMock(return_value=get_project_version())
        with (
            patch.object(BackgroundTasks, "add_task", side_effect=lambda *args, **kwargs: None),
            patch("plastered.api.webserver.get_lifespan_singleton", return_value=singleton_inst),
        ):
            yield singleton_inst


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app=fastapi_app) as test_client:
        yield test_client
