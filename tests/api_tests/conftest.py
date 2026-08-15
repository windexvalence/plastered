from typing import Generator
from unittest.mock import MagicMock, patch

from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
import pytest

from plastered.api.app import create_fastapi_app
from plastered.config.app_settings import AppSettings
from plastered.models.red_models import RedUserDetails
from plastered.release_search.release_searcher import ReleaseSearcher
from plastered.utils.http_clients.red_client import RedAPIClient


@pytest.fixture(scope="session", autouse=True)
def mock_lifespan_state(
    valid_app_settings_sesh_scoped: AppSettings, mock_red_user_details: RedUserDetails
) -> Generator[None, None, None]:
    """
    Patches the pieces `plastered.api.app._app_lifespan` builds at startup (settings load, the RED client, and the
    `ReleaseSearcher`) so app lifespans in these tests (e.g. the session-scoped `client`) never make real RED API
    calls (`RedAPIClient.get_red_user_details`). Only the names bound in the `plastered.api.app` module namespace are
    patched, so the real classes remain untouched for unrelated tests sharing the xdist worker
    (e.g. test_create_red_user_details).
    """
    mock_red_api_client = MagicMock(spec=RedAPIClient)
    mock_red_api_client.get_red_user_details.return_value = mock_red_user_details
    with (
        patch("plastered.api.app.get_app_settings", return_value=valid_app_settings_sesh_scoped),
        patch("plastered.api.app.RedAPIClient", return_value=mock_red_api_client),
        patch("plastered.api.app.ReleaseSearcher", return_value=MagicMock(spec=ReleaseSearcher)),
    ):
        yield


@pytest.fixture(autouse=True)
def _stub_background_tasks_add_task() -> Generator[None, None, None]:
    """
    Stub `BackgroundTasks.add_task` to a no-op for each api test so endpoints don't actually run scheduled work.
    Function-scoped (not held across the whole session) so the class patch can't leak onto other tests.
    """
    with patch.object(BackgroundTasks, "add_task", side_effect=lambda *args, **kwargs: None):
        yield


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app=create_fastapi_app()) as test_client:
        yield test_client
