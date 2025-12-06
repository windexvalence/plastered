from pathlib import Path
import re
from typing import Any
from unittest.mock import patch, ANY

from fastapi import HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from pytest_mock import MockerFixture

from plastered.api.api_models import RunHistoryItem, RunHistoryListResponse
from plastered.api.constants import SUB_CONF_NAMES, Endpoint
from plastered.config.app_settings import AppSettings
from plastered.db.db_models import Failed, Grabbed, SearchRecord, SkipReason, Skipped
from plastered.models.types import EntityType
from plastered.version import get_project_version


def test_healthcheck_endpoint(client: TestClient) -> None:
    expected_json = {"version": f"{get_project_version()}"}
    resp = client.get("/api/healthcheck")
    assert resp.status_code == 200
    assert resp.json() == expected_json


def test_show_config_endpoint(client: TestClient) -> None:
    with patch(
        "plastered.api.api_routes.show_config_action", return_value={"fake-key": "fake-value"}
    ) as mock_show_config_action:
        resp = client.get("/api/config")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json", f"{resp.headers=}"
        mock_show_config_action.assert_called_once()


@pytest.fixture(scope="session")
def mock_htmx_request_headers() -> dict[str, str]:
    return {"HX-Request": "true"}


@pytest.fixture(scope="session")
def mock_conf_dict() -> dict[str, Any]:
    return {"red": {sub_conf_name: "fake_value" for sub_conf_name in SUB_CONF_NAMES}}


@pytest.mark.parametrize(
    "sub_conf, expected_status_code",
    [(None, 200), ("format_preferences", 200), ("search", 200), ("snatches", 200), ("bad_key", 404)],
)
def test_show_config_endpoint_htmx(
    client: TestClient,
    mock_conf_dict: dict[str, Any],
    mock_htmx_request_headers: dict[str, str],
    sub_conf: str | None,
    expected_status_code: int,
) -> None:
    req_pathstr = "/api/config" + (f"?sub_conf={sub_conf}" if sub_conf else "")
    with (
        patch("plastered.api.api_routes.show_config_action", return_value=mock_conf_dict) as mock_show_config_action,
        patch.object(Jinja2Templates, "TemplateResponse") as mock_template_response_constructor,
    ):
        resp = client.get(req_pathstr, headers=mock_htmx_request_headers)
        assert resp.status_code == expected_status_code
        if expected_status_code == 200:
            mock_template_response_constructor.assert_called_once()
        mock_show_config_action.assert_called_once()


@pytest.mark.parametrize("mock_record_found", [False, True])
def test_inspect_run_endpoint(client: TestClient, mock_record_found: bool) -> None:
    mock_id = 69
    mock_record = (
        SearchRecord(
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
    with patch("plastered.api.api_routes.inspect_run_action", return_value=mock_record) as mock_inspect_fn:
        resp = client.get(f"/api/inspect_run?run_id={mock_id}")
        if mock_record_found:
            assert resp.status_code == 200
            assert resp.json() == mock_record.model_dump()
        else:
            assert resp.status_code == 404


@pytest.mark.parametrize(
    "form_data, request_params, expected_entity_type",
    [
        ({"entity": "fake-album", "artist": "fake-artist", "is_track": "false"}, None, EntityType.ALBUM),
        ({"entity": "fake-track", "artist": "fake-artist", "is_track": "true"}, "?is_track=true", EntityType.TRACK),
    ],
)
def test_submit_search_form_endpoint(
    client: TestClient, form_data: dict[str, str], request_params: str | None, expected_entity_type: EntityType
) -> None:
    with (
        patch("plastered.api.api_routes.manual_search_action", return_value={"fake": "data"}),
        patch(
            "plastered.api.api_routes.run_history_endpoint",
            return_value=RunHistoryListResponse(runs=[], since_timestamp=1759680000),
        ) as mock_run_history_endpoint,
    ):
        resp = client.post(f"/api/submit_search_form{request_params or ''}", data=form_data, follow_redirects=False)
        assert resp.status_code == 303


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
        patch("plastered.api.api_routes.scrape_action", return_value=None) as mock_scrape_action,
        patch("plastered.api.api_routes.get_app_settings", return_value=valid_app_settings) as mock_get_app_settings,
    ):
        resp = client.post(f"/api/scrape?snatch={str(snatch).lower()}&rec_type={rec_type}")
        assert resp.status_code == 200
        mock_get_app_settings.assert_called_once_with(
            Path(valid_config_filepath),
            cli_overrides={"SNATCH_ENABLED": snatch, "REC_TYPES": expected_rt_cli_override_arg},
        )
        mock_scrape_action.assert_called_once()


@pytest.mark.parametrize(
    "mock_response_model",
    [
        pytest.param(RunHistoryListResponse(runs=[], since_timestamp=1759680000), id="no-history"),
        pytest.param(
            RunHistoryListResponse(
                runs=[
                    RunHistoryItem(
                        searchrecord=SearchRecord(
                            id=69,
                            submit_timestamp=1759680001,
                            is_manual=True,
                            entity_type=EntityType.ALBUM,
                            artist="Fake Artist",
                            entity="Fake Album",
                        ),
                        skipped=Skipped(id=420, s_result_id=69, skip_reason=SkipReason.NO_MATCH_FOUND),
                    )
                ],
                since_timestamp=1759680000,
            ),
            id="single-history-entry",
        ),
        pytest.param(
            RunHistoryListResponse(
                runs=[
                    RunHistoryItem(
                        searchrecord=SearchRecord(
                            id=69,
                            submit_timestamp=1759680001,
                            is_manual=True,
                            entity_type=EntityType.ALBUM,
                            artist="Fake Artist",
                            entity="Fake Album",
                        ),
                        skipped=Skipped(id=420, s_result_id=69, skip_reason=SkipReason.NO_MATCH_FOUND),
                    ),
                    RunHistoryItem(
                        searchrecord=SearchRecord(
                            id=666,
                            submit_timestamp=1759680001,
                            is_manual=True,
                            entity_type=EntityType.TRACK,
                            artist="Faker Artist",
                            entity="Fake Track",
                        ),
                        grabbed=Grabbed(id=421, g_result_id=666, fl_token_used=False, tid=69420),
                    ),
                ],
                since_timestamp=1759680000,
            ),
            id="multi-history-entry",
        ),
    ],
)
def test_run_history_endpoint(client: TestClient, mock_response_model: RunHistoryListResponse) -> None:
    mock_since = 1759680000
    with patch(
        "plastered.api.api_routes.run_history_action", return_value=mock_response_model
    ) as mock_run_history_action:
        resp = client.get(f"/api/run_history?since_timestamp={mock_since}")
        assert resp.status_code == 200
        mock_run_history_action.assert_called_once_with(
            since_timestamp=mock_since, session=ANY, final_state=None, search_id=None
        )
