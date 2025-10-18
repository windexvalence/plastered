from pathlib import Path
from typing import Generator
from unittest.mock import patch, ANY

from fastapi.testclient import TestClient
import pytest

from plastered.api.server import fastapi_app, show_config_endpoint
from plastered.config.app_settings import AppSettings, get_app_settings
from plastered.db.db_models import SearchRun
from plastered.models.types import EntityType
from plastered.version import get_project_version


@pytest.fixture(scope="function")
def client(valid_app_settings: AppSettings) -> Generator[TestClient, None, None]:
    # fastapi_app.dependency_overrides[get_app_settings] = lambda x: valid_app_settings
    # https://fastapi.tiangolo.com/advanced/testing-events/
    with TestClient(app=fastapi_app) as test_client:
        yield test_client


def test_favicon_endpoint(client: TestClient) -> None:
    resp = client.get("/favicon.ico")
    assert resp.status_code == 200
    assert "image" in resp.headers["content-type"]


def test_root_endpoint(client: TestClient) -> None:
    expected_version = get_project_version()
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/html; charset=utf-8"
    assert f"<title>Plastered v{expected_version}</title>" in resp.text


def test_show_config_endpoint(valid_app_settings: AppSettings, client: TestClient) -> None:
    resp = client.get("/show_config")
    assert resp.status_code == 200
    resp_json = resp.json()
    assert set(resp_json.keys()) == set(valid_app_settings.model_dump().keys())


@pytest.mark.filterwarnings("ignore:.*not the first parameter anymore.*")
def test_search_form_endpoint(client: TestClient) -> None:
    resp = client.get("/search_form")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/html; charset=utf-8"


@pytest.mark.parametrize(
    "form_data, request_params, expected_entity_type",
    [
        ({"entity": "fake-album", "artist": "fake-artist"}, None, EntityType.ALBUM),
        ({"entity": "fake-track", "artist": "fake-artist"}, "?is_track=true", EntityType.TRACK),
    ],
)
def test_submit_search_form_endpoint(
    client: TestClient, form_data: dict[str, str], request_params: str | None, expected_entity_type: EntityType
) -> None:
    target_endpoint = f"/submit_search_form{request_params or ''}"
    with patch("plastered.api.server.manual_search_action", return_value={"fake": "data"}) as mock_manual_search_action:
        resp = client.post(target_endpoint, data=form_data)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/html; charset=utf-8"
        assert "<title>Search Submitted</title>" in resp.text
        mock_manual_search_action.assert_called_once()


@pytest.mark.parametrize("snatch", [False, True])
@pytest.mark.parametrize(
    "rec_type, expected_rt_cli_override_arg", [("track", ["track"]), ("album", ["album"]), ("all", ["album", "track"])]
)
def test_scrape_endpoint(
    valid_config_filepath: str,
    valid_app_settings: AppSettings,
    client: TestClient,
    snatch: bool,
    rec_type: str,
    expected_rt_cli_override_arg: list[str],
) -> None:
    with (
        patch("plastered.api.server.scrape_action", return_value=None) as mock_scrape_action,
        patch("plastered.api.server.get_app_settings", return_value=valid_app_settings) as mock_get_app_settings,
    ):
        resp = client.post(f"/scrape?snatch={str(snatch).lower()}&rec_type={rec_type}")
        assert resp.status_code == 200
        mock_get_app_settings.assert_called_once_with(
            Path(valid_config_filepath),
            cli_overrides={"SNATCH_ENABLED": snatch, "REC_TYPES": expected_rt_cli_override_arg},
        )
        mock_scrape_action.assert_called_once()


def test_run_history_endpoint(client: TestClient) -> None:
    mock_since = 1759680000
    with patch("plastered.api.server.run_history_action", return_value=[]) as mock_run_history_action:
        resp = client.get(f"/run_history?since_timestamp={mock_since}")
        assert resp.status_code == 200
        mock_run_history_action.assert_called_once_with(since_timestamp=mock_since, session=ANY)


@pytest.mark.parametrize("mock_record_found", [False, True])
def test_inspect_run_endpoint(client: TestClient, mock_record_found: bool) -> None:
    mock_id = 69
    mock_record = (
        SearchRun(
            id=mock_id,
            submit_timestamp=1759680000,
            is_manual=True,
            entity_type=EntityType.ALBUM,
            artist="Fake Artist",
            entity="Fake Name",
        )
        if mock_record_found
        else None
    )
    with patch("plastered.api.server.inspect_run_action", return_value=mock_record) as mock_inspect_fn:
        resp = client.get(f"/inspect_run?run_id={mock_id}")
        if mock_record_found:
            assert resp.status_code == 200
            assert resp.json() == mock_record.model_dump()
        else:
            assert resp.status_code == 404
