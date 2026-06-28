from typing import Final
from unittest.mock import ANY, MagicMock, patch

from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient
import pytest

from plastered.api.api_models import AdhocSearchResult
from plastered.config.app_settings import AppSettings
from plastered.db.db_models import Failed, FailReason, Grabbed, Matched, SearchRecord, Skipped, SkipReason, Status
from plastered.models.types import EntityType
from plastered.version import get_project_version


_EXPECTED_HTML_CONTENT_TYPE: Final[str] = "text/html; charset=utf-8"


def test_favicon_endpoint(client: TestClient) -> None:
    resp = client.get("/favicon.ico")
    assert resp.status_code == 200
    assert "image" in resp.headers["content-type"]


def test_wood_background_asset_served(client: TestClient) -> None:
    """The wood background image is served and the stylesheet references it via a valid url() (guards the bare-string regression)."""
    img = client.get("/static/images/wood.jpg")
    assert img.status_code == 200
    assert "image" in img.headers["content-type"]
    css = client.get("/static/css/classless.css")
    assert css.status_code == 200
    assert 'url("/static/images/wood.jpg")' in css.text


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


def test_adhoc_search_page(client: TestClient) -> None:
    # Render for real (no TemplateResponse patch) to validate adhoc_search.html + base_template.html.
    resp = client.get("/adhoc")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == _EXPECTED_HTML_CONTENT_TYPE
    assert "Ad-hoc RED Search" in resp.text


@pytest.mark.parametrize(
    "form_data",
    [
        {"artist": "Fake Artist", "release": "Fake Album"},
        {"artist": "Fake Artist", "track": "Fake Track", "snatch": "true"},
    ],
)
def test_adhoc_search_submit(client: TestClient, form_data: dict[str, str]) -> None:
    with (
        patch("plastered.api.routes.webserver_routes.schedule_adhoc_search", return_value=69) as mock_schedule,
        patch.object(Jinja2Templates, "TemplateResponse") as mock_template_response_constructor,
    ):
        resp = client.post("/adhoc_search", data=form_data)
        assert resp.status_code == 200
        mock_schedule.assert_called_once()
        mock_template_response_constructor.assert_called_once()


def test_adhoc_search_submit_invalid(client: TestClient) -> None:
    """Submitting a form with neither release nor track is rejected (422)."""
    resp = client.post("/adhoc_search", data={"artist": "Fake Artist"})
    assert resp.status_code == 422


def test_adhoc_result_fragment_missing(client: TestClient) -> None:
    with patch("plastered.api.routes.webserver_routes.adhoc_result_action", return_value=None):
        resp = client.get("/adhoc_result?search_id=404")
        assert resp.status_code == 404


def _adhoc_result(status: Status, **status_rows: object) -> AdhocSearchResult:
    record = SearchRecord(
        id=69,
        submit_timestamp=1759680000,
        is_manual=True,
        entity_type=EntityType.ALBUM,
        artist="Fake Artist",
        entity="Fake Album",
        status=status,
    )
    return AdhocSearchResult(searchrecord=record, **status_rows)


@pytest.mark.parametrize(
    "result, expected_snippet",
    [
        (_adhoc_result(Status.IN_PROGRESS), "Searching RED"),
        (
            _adhoc_result(
                Status.MATCHED,
                matched=Matched(
                    m_result_id=69,
                    tid=420,
                    red_permalink="https://red/x",
                    size_gb=1.0,
                    media="WEB",
                    format="FLAC",
                    encoding="Lossless",
                ),
            ),
            "Matched a release",
        ),
        (
            _adhoc_result(
                Status.GRABBED,
                grabbed=Grabbed(g_result_id=69, fl_token_used=False, snatch_path="/d/420.torrent", tid=420),
            ),
            "downloaded",
        ),
        (
            _adhoc_result(Status.SKIPPED, skipped=Skipped(s_result_id=69, skip_reason=SkipReason.NO_MATCH_FOUND)),
            "No matching release was snatched",
        ),
        (_adhoc_result(Status.FAILED, failed=Failed(f_result_id=69, fail_reason=FailReason.OTHER)), "Search failed"),
    ],
)
def test_adhoc_result_fragment_renders(client: TestClient, result: AdhocSearchResult, expected_snippet: str) -> None:
    # Render for real to validate the fragment template across the in-progress + each terminal status branch.
    with patch("plastered.api.routes.webserver_routes.adhoc_result_action", return_value=result):
        resp = client.get("/adhoc_result?search_id=69")
        assert resp.status_code == 200
        assert expected_snippet in resp.text


def test_scrape_form_endpoint(client: TestClient) -> None:
    resp = client.get("/scrape_form")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == _EXPECTED_HTML_CONTENT_TYPE


def test_runs_page(client: TestClient) -> None:
    with patch.object(Jinja2Templates, "TemplateResponse") as mock_template_response_constructor:
        resp = client.get("/run_history")
        assert resp.status_code == 200
        mock_template_response_constructor.assert_called_once()


def test_user_details_page(client: TestClient) -> None:
    with patch.object(Jinja2Templates, "TemplateResponse") as mock_template_response_constructor:
        resp = client.get("/user_details")
        assert resp.status_code == 200
        mock_template_response_constructor.assert_called_once_with(
            request=ANY, name="user_details.html", context={"user_id": ANY, "available_fl_tokens": ANY}
        )


def test_result_modal(client: TestClient) -> None:
    with patch.object(Jinja2Templates, "TemplateResponse") as mock_template_response_constructor:
        resp = client.get("/result_modal")
        assert resp.status_code == 200
        mock_template_response_constructor.assert_called_once()
