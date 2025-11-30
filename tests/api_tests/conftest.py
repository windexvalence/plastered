from typing import Generator
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from plastered.api.fastapi_dependencies import _DependencySingletons
from plastered.api.webserver import fastapi_app
from plastered.config.app_settings import AppSettings
from plastered.models.red_models import RedUserDetails


@pytest.fixture(scope="session", autouse=True)
def mock_DependencySingletons_inst(
    valid_app_settings_sesh_scoped: AppSettings, mock_red_user_details: RedUserDetails
) -> Generator[None, None, None]:
    from fastapi import BackgroundTasks

    with (
        patch.object(BackgroundTasks, "add_task", side_effect=lambda *args, **kwargs: None),
        patch.object(_DependencySingletons, "get_app_settings_instance", return_value=valid_app_settings_sesh_scoped),
        patch.object(_DependencySingletons, "get_red_user_details_instance", return_value=mock_red_user_details),
        patch.object(_DependencySingletons, "get_project_version_instance", return_value="x.y.z"),
    ):
        yield


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app=fastapi_app) as test_client:
        yield test_client
