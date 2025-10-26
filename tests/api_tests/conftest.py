from typing import Generator

from fastapi.testclient import TestClient
import pytest

from plastered.api.webserver import fastapi_app
from plastered.config.app_settings import AppSettings


# TODO: see if this can be session-scoped
@pytest.fixture(scope="function")
def client(valid_app_settings: AppSettings) -> Generator[TestClient, None, None]:
    # fastapi_app.dependency_overrides[get_app_settings] = lambda x: valid_app_settings
    # https://fastapi.tiangolo.com/advanced/testing-events/
    with TestClient(app=fastapi_app) as test_client:
        yield test_client
