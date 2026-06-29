from typing import Generator
from unittest.mock import MagicMock, PropertyMock, patch

from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
import pytest

from plastered.api.lifespan_resources import LifespanSingleton
from plastered.api.main import fastapi_app
from plastered.config.app_settings import AppSettings
from plastered.models.red_models import RedUserDetails
from plastered.release_search.release_searcher import ReleaseSearcher
from plastered.utils.httpx_utils.red_client import RedAPIClient
from plastered.version import get_project_version


@pytest.fixture(scope="session", autouse=True)
def mock_LifespanSingleton_inst(
    request: pytest.FixtureRequest, valid_app_settings_sesh_scoped: AppSettings, mock_red_user_details: RedUserDetails
) -> Generator[LifespanSingleton, None, None]:
    if "no_autouse_mock_lifespan_singleton_inst" in request.keywords:
        return

    singleton_inst = MagicMock(spec=LifespanSingleton)
    type(singleton_inst).app_settings = PropertyMock(return_value=valid_app_settings_sesh_scoped)
    type(singleton_inst).config_filepath = PropertyMock(return_value=valid_app_settings_sesh_scoped.src_yaml_filepath)
    mock_red_api_client = MagicMock(spec=RedAPIClient)
    mock_red_api_client.get_red_user_details.return_value = mock_red_user_details
    type(singleton_inst).red_api_client = PropertyMock(return_value=mock_red_api_client)
    type(singleton_inst).red_user_details = PropertyMock(return_value=mock_red_user_details)
    type(singleton_inst).release_searcher = PropertyMock(return_value=MagicMock(spec=ReleaseSearcher))
    type(singleton_inst).project_version = PropertyMock(return_value=get_project_version())
    # Only `get_lifespan_singleton` is patched here (needed for the session-scoped `client` app lifespan). The real
    # `LifespanSingleton.__post_init__` (the only caller of `RedAPIClient.get_red_user_details`) never runs because of
    # this patch, so there is no need to patch the RED client itself — doing so at session scope previously leaked the
    # mock onto unrelated tests sharing the xdist worker (e.g. test_create_red_user_details).
    with patch("plastered.api.main.get_lifespan_singleton", return_value=singleton_inst):
        yield singleton_inst


@pytest.fixture(autouse=True)
def _stub_background_tasks_add_task(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """
    Stub `BackgroundTasks.add_task` to a no-op for each api test so endpoints don't actually run scheduled work.
    Function-scoped (not held across the whole session) so the class patch can't leak onto other tests.
    """
    if "no_autouse_mock_lifespan_singleton_inst" in request.keywords:
        yield
        return
    with patch.object(BackgroundTasks, "add_task", side_effect=lambda *args, **kwargs: None):
        yield


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app=fastapi_app) as test_client:
        yield test_client
