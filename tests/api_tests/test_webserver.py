from typing import Final
from unittest.mock import ANY, MagicMock, patch

from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient
import pytest

from plastered.api.api_models import AdhocSearchResult, RunHistoryItem, RunHistoryPageResponse, RunHistoryRow
from plastered.api.constants import _format_timestamp, _status_label
from plastered.config.app_settings import AppSettings
from plastered.db.db_models import (
    Failed,
    FailReason,
    Grabbed,
    Matched,
    RecDownloadBatch,
    RecDownloadBatchStatus,
    ScraperRun,
    ScraperRunStatus,
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
    for path in ("/run_history", "/lfm_recommendations_scraper", "/config"):
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


def test_lfm_scraper_page(client: TestClient) -> None:
    # Render for real to validate lfm_scraper.html + its controls.
    resp = client.get("/lfm_recommendations_scraper")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == _EXPECTED_HTML_CONTENT_TYPE
    assert "Last.fm Recommendations Scraper" in resp.text
    assert 'name="rec_type"' in resp.text and 'name="snatch"' in resp.text


@pytest.mark.parametrize("form_data", [{}, {"rec_type": "album", "snatch": "true"}])
def test_lfm_scraper_run_submit(client: TestClient, form_data: dict[str, str]) -> None:
    """Submitting the scraper form creates a ScraperRun and returns the status fragment (background task stubbed)."""
    with (
        patch("plastered.api.routes.webserver_routes.create_scraper_run", return_value=7) as mock_create,
        patch(
            "plastered.api.routes.webserver_routes.get_scraper_run_action",
            return_value=ScraperRun(id=7, submit_timestamp=1759680000, snatch_enabled=False, rec_types="album"),
        ),
    ):
        resp = client.post("/lfm_scraper_run", data=form_data)
        assert resp.status_code == 200
        mock_create.assert_called_once()


@pytest.mark.parametrize("found", [True, False])
def test_lfm_scraper_status_fragment(client: TestClient, found: bool) -> None:
    run = (
        ScraperRun(
            id=7,
            submit_timestamp=1759680000,
            snatch_enabled=True,
            rec_types="album,track",
            status=ScraperRunStatus.IN_PROGRESS,
            stage="searching",
            progress_current=2,
            progress_total=5,
        )
        if found
        else None
    )
    with patch("plastered.api.routes.webserver_routes.get_scraper_run_action", return_value=run):
        resp = client.get("/lfm_scraper_status?run_id=7")
        assert resp.status_code == (200 if found else 404)
        if found:
            assert "processing recommendation" in resp.text
            assert '<progress value="2" max="5">' in resp.text


@pytest.mark.parametrize(
    "run, expected_snippet",
    [
        (
            ScraperRun(
                id=1,
                submit_timestamp=1,
                snatch_enabled=False,
                rec_types="album",
                status=ScraperRunStatus.IN_PROGRESS,
                stage="scraping",
            ),
            "Scraping Last.fm",
        ),
        (
            ScraperRun(
                id=1,
                submit_timestamp=1,
                snatch_enabled=True,
                rec_types="album,track",
                status=ScraperRunStatus.COMPLETED,
                total_recs=12,
            ),
            "Scrape complete",
        ),
        (
            ScraperRun(
                id=1,
                submit_timestamp=1,
                snatch_enabled=False,
                rec_types="album",
                status=ScraperRunStatus.FAILED,
                error="boom",
            ),
            "Scrape failed",
        ),
    ],
)
def test_lfm_scraper_status_fragment_renders_stages(client: TestClient, run: ScraperRun, expected_snippet: str) -> None:
    with patch("plastered.api.routes.webserver_routes.get_scraper_run_action", return_value=run):
        text = client.get("/lfm_scraper_status?run_id=1").text
    assert expected_snippet in text


def test_runs_page(client: TestClient) -> None:
    # Render for real to validate run_history_page.html + its filter/sort controls.
    resp = client.get("/run_history")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == _EXPECTED_HTML_CONTENT_TYPE
    assert "Plastered Run History" in resp.text
    assert 'id="run-history-controls"' in resp.text
    assert 'id="run-history-list"' in resp.text


def _run_history_page(rows: list[RunHistoryRow], **kwargs: object) -> RunHistoryPageResponse:
    defaults = dict(page=1, page_size=50, total_count=len(rows), total_pages=1, sort_desc=True)
    defaults.update(kwargs)
    return RunHistoryPageResponse(rows=rows, **defaults)  # type: ignore[arg-type]


def _adhoc_row(**rec_kwargs: object) -> RunHistoryRow:
    rec = SearchRecord(**rec_kwargs)  # type: ignore[arg-type]
    return RunHistoryRow(kind="adhoc", sort_timestamp=rec.submit_timestamp, adhoc=RunHistoryItem(searchrecord=rec))


def test_run_history_list_fragment_renders_accordion(client: TestClient) -> None:
    """The fragment renders one accordion row per run with the summary line and a Next page control."""
    grabbed_rec = SearchRecord(
        id=1,
        submit_timestamp=1759680000,
        is_manual=True,
        entity_type=EntityType.ALBUM,
        artist="Aphex Twin",
        entity="Drukqs",
        status=Status.GRABBED,
    )
    rows = [
        RunHistoryRow(
            kind="adhoc",
            sort_timestamp=grabbed_rec.submit_timestamp,
            adhoc=RunHistoryItem(
                searchrecord=grabbed_rec,
                grabbed=Grabbed(g_result_id=1, fl_token_used=True, snatch_path="/d/1.torrent", tid=11),
            ),
        )
    ]
    page = _run_history_page(rows, page=1, page_size=1, total_count=2, total_pages=2)
    with patch("plastered.api.routes.webserver_routes.run_history_page_action", return_value=page):
        text = client.get("/run_history_list").text
    assert "<details" in text
    assert "Artist: <strong>Aphex Twin</strong>" in text
    assert "Status: <strong>snatched</strong>" in text  # grabbed -> snatched label
    assert "Next →" in text  # page 1 of 2 -> Next control present


def test_run_history_list_fragment_renders_scraper_run_row(client: TestClient) -> None:
    """A scraper run renders as a distinctly-styled accordion row that nests the recs it pulled."""
    scraper_run = ScraperRun(
        id=3,
        submit_timestamp=1759680000,
        finished_timestamp=1759680100,
        snatch_enabled=True,
        rec_types="album,track",
        status=ScraperRunStatus.COMPLETED,
        total_recs=1,
    )
    nested_rec = SearchRecord(
        id=9,
        submit_timestamp=1759680050,
        is_manual=False,
        entity_type=EntityType.ALBUM,
        artist="Scraped Artist",
        entity="Scraped Album",
        status=Status.SKIPPED,
    )
    rows = [
        RunHistoryRow(
            kind="scraper",
            sort_timestamp=scraper_run.submit_timestamp,
            scraper=scraper_run,
            scraper_recs=[RunHistoryItem(searchrecord=nested_rec)],
        )
    ]
    page = _run_history_page(rows)
    with patch("plastered.api.routes.webserver_routes.run_history_page_action", return_value=page):
        text = client.get("/run_history_list").text
    assert 'class="scraper-run"' in text  # distinct styling hook
    assert "LFM scraper run" in text
    assert "Recommendations pulled (1)" in text
    assert "Scraped Artist" in text  # nested rec shown on expand


def _scraper_recs(snatch_enabled: bool, batch: RecDownloadBatch | None = None):
    run = ScraperRun(
        id=5,
        submit_timestamp=1759680000,
        finished_timestamp=1759680100,
        snatch_enabled=snatch_enabled,
        rec_types="album",
        status=ScraperRunStatus.COMPLETED,
        total_recs=2,
    )
    matched_rec = RunHistoryItem(
        searchrecord=SearchRecord(
            id=10,
            submit_timestamp=1759680010,
            is_manual=False,
            entity_type=EntityType.ALBUM,
            artist="Matched Artist",
            entity="Matched Album",
            status=Status.MATCHED,
        ),
        matched=Matched(m_result_id=10, tid=100, red_permalink="https://red/100", size_gb=1.0),
    )
    skipped_rec = RunHistoryItem(
        searchrecord=SearchRecord(
            id=11,
            submit_timestamp=1759680011,
            is_manual=False,
            entity_type=EntityType.ALBUM,
            artist="Skipped Artist",
            entity="Skipped Album",
            status=Status.SKIPPED,
        )
    )
    return run, [matched_rec, skipped_rec], batch


def test_scraper_run_recs_fragment_interactive_for_disabled_downloads(client: TestClient) -> None:
    """A downloads-disabled run with a matched rec shows the Download Match? column + checkbox + batch controls."""
    with patch("plastered.api.routes.webserver_routes.scraper_run_recs_action", return_value=_scraper_recs(False)):
        text = client.get("/scraper_run_recs?run_id=5").text
    assert "Download Match?" in text
    assert 'name="search_ids" value="10"' in text  # checkbox for the matched rec
    assert "Snatch selected recs" in text
    assert "Download all (1)" in text


def test_scraper_run_recs_fragment_readonly_when_downloads_enabled(client: TestClient) -> None:
    """A downloads-enabled run shows a read-only recs table (no download controls)."""
    with patch("plastered.api.routes.webserver_routes.scraper_run_recs_action", return_value=_scraper_recs(True)):
        text = client.get("/scraper_run_recs?run_id=5").text
    assert "Download Match?" not in text
    assert "Snatch selected recs" not in text


def test_scraper_run_recs_fragment_shows_batch_progress(client: TestClient) -> None:
    batch = RecDownloadBatch(id=1, scraper_run_id=5, submit_timestamp=1, total=2, completed=1)
    with patch(
        "plastered.api.routes.webserver_routes.scraper_run_recs_action", return_value=_scraper_recs(False, batch)
    ):
        text = client.get("/scraper_run_recs?run_id=5").text
    assert "Downloading selected recommendations" in text
    assert '<progress value="1" max="2">' in text


def test_scraper_run_recs_fragment_missing(client: TestClient) -> None:
    with patch("plastered.api.routes.webserver_routes.scraper_run_recs_action", return_value=None):
        assert client.get("/scraper_run_recs?run_id=999").status_code == 404


@pytest.mark.parametrize("download_all", [False, True])
def test_scraper_run_snatch_submit_schedules_batch(client: TestClient, download_all: bool) -> None:
    run = _scraper_recs(False)[0]
    with (
        patch("plastered.api.routes.webserver_routes.get_scraper_run_action", return_value=run),
        patch("plastered.api.routes.webserver_routes.scraper_run_matched_rec_ids", return_value=[10]),
        patch("plastered.api.routes.webserver_routes.get_latest_rec_download_batch", return_value=None),
        patch("plastered.api.routes.webserver_routes.create_rec_download_batch", return_value=1) as mock_create,
        patch("plastered.api.routes.webserver_routes.scraper_run_recs_action", return_value=_scraper_recs(False)),
    ):
        data = {"run_id": "5"}
        if download_all:
            data["download_all"] = "true"
        else:
            data["search_ids"] = "10"
        resp = client.post("/scraper_run_snatch", data=data)
        assert resp.status_code == 200
        mock_create.assert_called_once()  # a download batch was created + scheduled


def test_scraper_run_snatch_submit_noop_when_nothing_selected(client: TestClient) -> None:
    run = _scraper_recs(False)[0]
    with (
        patch("plastered.api.routes.webserver_routes.get_scraper_run_action", return_value=run),
        patch("plastered.api.routes.webserver_routes.scraper_run_matched_rec_ids", return_value=[10]),
        patch("plastered.api.routes.webserver_routes.get_latest_rec_download_batch", return_value=None),
        patch("plastered.api.routes.webserver_routes.create_rec_download_batch", return_value=1) as mock_create,
        patch("plastered.api.routes.webserver_routes.scraper_run_recs_action", return_value=_scraper_recs(False)),
    ):
        # No checkbox selected and not download_all -> nothing to snatch.
        resp = client.post("/scraper_run_snatch", data={"run_id": "5"})
        assert resp.status_code == 200
        mock_create.assert_not_called()


def test_scraper_run_snatch_submit_missing_run(client: TestClient) -> None:
    with patch("plastered.api.routes.webserver_routes.get_scraper_run_action", return_value=None):
        assert client.post("/scraper_run_snatch", data={"run_id": "999"}).status_code == 404


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
    assert isinstance(_format_timestamp(1759680000), str) and len(_format_timestamp(1759680000)) == len(
        "2025-01-01 00:00:00"
    )


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
