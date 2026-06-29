from typing import Final
from unittest.mock import ANY, MagicMock, patch

from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient
import pytest

from plastered.api.api_models import AdhocSearchResult, RunHistoryItem, RunHistoryPageResponse
from plastered.api.constants import _format_timestamp, _status_label
from plastered.config.app_settings import AppSettings
from plastered.db.db_models import (
    Failed,
    FailReason,
    Grabbed,
    Matched,
    SearchProgress,
    SearchRecord,
    Skipped,
    SkipReason,
    Status,
)
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
    # Header Help button (from the base template) + the big home-page Help button both reference the help modal.
    assert 'id="header-help-btn"' in resp.text
    assert resp.text.count("/html/help_modal.html") >= 2


def test_header_help_button_present_on_all_pages(client: TestClient) -> None:
    """The shared header's red Help button (opening the help modal) appears on every base-template page."""
    for path in ("/run_history", "/scrape_form", "/config"):
        text = client.get(path).text
        assert 'id="header-help-btn"' in text
        assert "/html/help_modal.html" in text


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
            "Downloaded the matched release",
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


def test_adhoc_result_fragment_shows_progress_bar(client: TestClient) -> None:
    """An in-flight search with recorded progress renders a determinate progress bar + the format-preference suffix."""
    result = _adhoc_result(
        Status.IN_PROGRESS,
        progress=SearchProgress(
            sp_result_id=69, current_pref=1, total_prefs=2, current_pref_label="FLAC / 24bit Lossless / SACD"
        ),
    )
    with patch("plastered.api.routes.webserver_routes.adhoc_result_action", return_value=result):
        text = client.get("/adhoc_result?search_id=69").text
    assert "searching format preference:" in text
    assert "FLAC / 24bit Lossless / SACD" in text
    assert '<progress value="1" max="2">' in text


def test_adhoc_result_fragment_matched_shows_download_button(client: TestClient) -> None:
    """A search-only (MATCHED) result offers a per-result Download button; a downloaded (GRABBED) result does not."""
    matched_result = _adhoc_result(
        Status.MATCHED, matched=Matched(m_result_id=69, tid=420, red_permalink="https://red/x", size_gb=1.0)
    )
    grabbed_result = _adhoc_result(
        Status.GRABBED, grabbed=Grabbed(g_result_id=69, fl_token_used=False, snatch_path="/d/420.torrent", tid=420)
    )
    with patch("plastered.api.routes.webserver_routes.adhoc_result_action", return_value=matched_result):
        matched_text = client.get("/adhoc_result?search_id=69").text
    with patch("plastered.api.routes.webserver_routes.adhoc_result_action", return_value=grabbed_result):
        grabbed_text = client.get("/adhoc_result?search_id=69").text
    assert 'hx-post="/adhoc_snatch"' in matched_text
    assert "Download this release" in matched_text
    assert "/adhoc_snatch" not in grabbed_text


@pytest.mark.parametrize("record_found", [True, False])
def test_adhoc_snatch_submit(client: TestClient, record_found: bool) -> None:
    mock_result = (
        _adhoc_result(
            Status.GRABBED, grabbed=Grabbed(g_result_id=69, fl_token_used=False, snatch_path="/d/420.torrent", tid=420)
        )
        if record_found
        else None
    )
    with (
        patch("plastered.api.routes.webserver_routes.adhoc_snatch_action", return_value=mock_result) as mock_snatch,
        patch.object(Jinja2Templates, "TemplateResponse") as mock_template_response_constructor,
    ):
        resp = client.post("/adhoc_snatch", data={"search_id": "69"})
        assert resp.status_code == (200 if record_found else 404)
        mock_snatch.assert_called_once()
        if record_found:
            mock_template_response_constructor.assert_called_once()


def test_scrape_form_endpoint(client: TestClient) -> None:
    resp = client.get("/scrape_form")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == _EXPECTED_HTML_CONTENT_TYPE


def test_runs_page(client: TestClient) -> None:
    # Render for real to validate run_history_page.html + its filter/sort controls.
    resp = client.get("/run_history")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == _EXPECTED_HTML_CONTENT_TYPE
    assert "Plastered Run History" in resp.text
    assert 'id="run-history-controls"' in resp.text
    assert 'id="run-history-list"' in resp.text


def _run_history_page(items: list[RunHistoryItem], **kwargs: object) -> RunHistoryPageResponse:
    defaults = dict(page=1, page_size=50, total_count=len(items), total_pages=1, sort_desc=True)
    defaults.update(kwargs)
    return RunHistoryPageResponse(items=items, **defaults)  # type: ignore[arg-type]


def test_run_history_list_fragment_renders_accordion(client: TestClient) -> None:
    """The fragment renders one accordion row per run with the summary line and a Next page control."""
    items = [
        RunHistoryItem(
            searchrecord=SearchRecord(
                id=1, submit_timestamp=1759680000, is_manual=True, entity_type=EntityType.ALBUM,
                artist="Aphex Twin", entity="Drukqs", status=Status.GRABBED,
            ),
            grabbed=Grabbed(g_result_id=1, fl_token_used=True, snatch_path="/d/1.torrent", tid=11),
        ),
        RunHistoryItem(
            searchrecord=SearchRecord(
                id=2, submit_timestamp=1759680001, is_manual=False, entity_type=EntityType.TRACK,
                artist="Autechre", entity="Gantz Graf", status=Status.SKIPPED,
            ),
            skipped=Skipped(s_result_id=2, skip_reason=SkipReason.NO_MATCH_FOUND),
        ),
    ]
    page = _run_history_page(items, page=1, page_size=2, total_count=4, total_pages=2)
    with patch("plastered.api.routes.webserver_routes.run_history_page_action", return_value=page):
        text = client.get("/run_history_list").text
    assert "<details" in text
    assert "Artist: <strong>Aphex Twin</strong>" in text
    assert "Status: <strong>snatched</strong>" in text  # grabbed -> snatched label
    assert "Status: <strong>skipped</strong>" in text
    assert "Next →" in text  # page 1 of 2 -> Next control present


def test_run_history_list_fragment_empty(client: TestClient) -> None:
    page = _run_history_page([])
    with patch("plastered.api.routes.webserver_routes.run_history_page_action", return_value=page):
        text = client.get("/run_history_list").text
    assert "No runs found." in text


def test_run_history_list_endpoint_passes_filters(client: TestClient) -> None:
    page = _run_history_page([])
    with patch("plastered.api.routes.webserver_routes.run_history_page_action", return_value=page) as mock_action:
        client.get("/run_history_list?page=3&status=grabbed&q=foo&sort=asc")
    kwargs = mock_action.call_args.kwargs
    assert kwargs["page"] == 3
    assert kwargs["status_filter"] == Status.GRABBED
    assert kwargs["query"] == "foo"
    assert kwargs["sort_desc"] is False


def test_run_history_list_endpoint_ignores_blank_and_invalid_status(client: TestClient) -> None:
    page = _run_history_page([])
    with patch("plastered.api.routes.webserver_routes.run_history_page_action", return_value=page) as mock_action:
        client.get("/run_history_list?status=&q=")
    kwargs = mock_action.call_args.kwargs
    assert kwargs["status_filter"] is None
    assert kwargs["query"] is None


def test_format_timestamp_filter() -> None:
    assert _format_timestamp(None) == "—"
    assert isinstance(_format_timestamp(1759680000), str) and len(_format_timestamp(1759680000)) == len("2025-01-01 00:00:00")


def test_status_label_filter() -> None:
    assert _status_label(None) == "unknown"
    assert _status_label(Status.GRABBED) == "snatched"
    assert _status_label(Status.MATCHED) == "found"
    assert _status_label(Status.IN_PROGRESS) == "in progress"
    assert _status_label("some-unmapped-value") == "some-unmapped-value"


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
