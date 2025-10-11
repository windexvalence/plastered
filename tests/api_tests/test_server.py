from pathlib import Path
from typing import Generator
from unittest.mock import patch, ANY

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse, Response
from fastapi.testclient import TestClient
import pytest

from plastered.api.server import fastapi_app, show_config_endpoint
from plastered.config.app_settings import AppSettings, get_app_settings
from plastered.version import get_project_version


@pytest.fixture(scope="function")
def client(valid_app_settings: AppSettings) -> Generator[TestClient, None, None]:
    # fastapi_app.dependency_overrides[get_app_settings] = lambda x: valid_app_settings
    # https://fastapi.tiangolo.com/advanced/testing-events/
    with TestClient(app=fastapi_app) as test_client:
        yield test_client


def test_root_endpoint(client: TestClient) -> None:
    expected_version = get_project_version()
    resp = client.get("/")
    assert resp.status_code == 200
    resp_json = resp.json()
    assert "message" in resp_json
    assert resp_json["message"] == f"Plastered {expected_version}"


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


@pytest.mark.asyncio
async def test_submit_album_search_form_endpoint(client: TestClient) -> None:
    mock_album = "fake-album"
    mock_artist = "fake-artist"
    with patch("plastered.api.server.manual_search_action", return_value={"fake": "data"}) as mock_manual_search_action:
        resp = client.post("/submit_album_search_form", data={"album": mock_album, "artist": mock_artist})
        assert resp.status_code == 200
        mock_manual_search_action.assert_called_once()
        pass  # TODO: implement


@pytest.mark.asyncio
async def test_submit_track_search_form_endpoint(client: TestClient) -> None:
    mock_track = "fake-track"
    mock_artist = "fake-artist"
    resp = client.post("/submit_track_search_form", data={"track": mock_track, "artist": mock_artist})
    assert resp.status_code == 200
    pass  # TODO: implement real test here


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


def test_inspect_run_endpoint(client: TestClient) -> None:
    resp = client.get("/inspect_run?run_id=foo")
    assert resp.status_code == 418
