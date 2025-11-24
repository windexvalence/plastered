from typing import Final
from unittest.mock import patch

from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient
import pytest
from starlette.routing import Mount

from plastered.config.app_settings import AppSettings
from plastered.models.types import EntityType
from plastered.version import get_project_version


_EXPECTED_HTML_CONTENT_TYPE: Final[str] = "text/html; charset=utf-8"


def test_sub_app_mounts(client: TestClient) -> None:
    """Ensures the expected sub-applications are mounted to the main app defined in server.py"""
    from plastered.api.api_routes import plastered_api_router

    expected_sub_app_path_prefixes: set[str] = {"/api", "/static"}
    main_app = client.app
    assert main_app is not None
    for route in main_app.router.routes:
        if isinstance(route, Mount):
            assert route.path in expected_sub_app_path_prefixes


def test_favicon_endpoint(client: TestClient) -> None:
    resp = client.get("/favicon.ico")
    assert resp.status_code == 200
    assert "image" in resp.headers["content-type"]


def test_root_endpoint(client: TestClient) -> None:
    expected_version = get_project_version()
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == _EXPECTED_HTML_CONTENT_TYPE
    assert f"<title>Plastered v{expected_version}</title>" in resp.text


def test_show_config_endpoint(valid_app_settings: AppSettings, client: TestClient) -> None:
    resp = client.get("/config")
    assert resp.status_code == 200
    resp.headers["content-type"] == _EXPECTED_HTML_CONTENT_TYPE
    assert "<title>Plastered Config</title>" in resp.text


@pytest.mark.parametrize("entity_type", [None, EntityType.ALBUM, EntityType.TRACK])
@pytest.mark.filterwarnings("ignore:.*not the first parameter anymore.*")
def test_search_form_endpoint(client: TestClient, entity_type: EntityType | None) -> None:
    req_pathstr = "/search_form" + (f"?entity={str(entity_type)}" if entity_type else "")
    with patch.object(Jinja2Templates, "TemplateResponse") as mock_template_response_constructor:
        resp = client.get(req_pathstr)
        assert resp.status_code == 200
        mock_template_response_constructor.assert_called_once()
        # assert resp.headers["content-type"] == _EXPECTED_HTML_CONTENT_TYPE


def test_scrape_form_endpoint(client: TestClient) -> None:
    resp = client.get("/scrape_form")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == _EXPECTED_HTML_CONTENT_TYPE


def test_runs_page(client: TestClient) -> None:
    with patch.object(Jinja2Templates, "TemplateResponse") as mock_template_response_constructor:
        resp = client.get("/run_history")
        assert resp.status_code == 200
        mock_template_response_constructor.assert_called_once()


def test_result_modal(client: TestClient) -> None:
    with patch.object(Jinja2Templates, "TemplateResponse") as mock_template_response_constructor:
        resp = client.get("/result_modal")
        assert resp.status_code == 200
        mock_template_response_constructor.assert_called_once()
