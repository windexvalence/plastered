from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from plastered.actions.common_actions import run_lfm_scraper, scrape_action, show_config_action
from plastered.config.app_settings import AppSettings
from plastered.db.db_models import ScraperRunStatus
from plastered.models.types import EntityType
from plastered.release_search.release_searcher import ReleaseSearcher
from plastered.scraper.lfm_scraper import LFMRecsScraper


def test_show_config_action(valid_app_settings: AppSettings) -> None:
    with patch.object(AppSettings, "model_dump_json", return_value='{"mock": "data"}') as mock_app_settings_model_dump:
        _ = show_config_action(app_settings=valid_app_settings)
        mock_app_settings_model_dump.assert_called_once()


def test_scrape_action(valid_app_settings: AppSettings) -> None:
    mock_scraper = MagicMock(spec=LFMRecsScraper)
    mock_scraper.scrape_recs.return_value = {}
    with (
        patch.object(LFMRecsScraper, "__enter__", return_value=mock_scraper) as mock_scraper_enter,
        patch("plastered.actions.common_actions.ReleaseSearcher") as mock_searcher_new,
        patch("plastered.actions.common_actions.create_scraper_run", return_value=7) as mock_create_run,
        patch("plastered.actions.common_actions.update_scraper_run") as mock_update_run,
    ):
        mock_searcher = mock_searcher_new.return_value
        scrape_action(app_settings=valid_app_settings)
        mock_create_run.assert_called_once()  # the scrape is recorded as a ScraperRun
        mock_scraper_enter.assert_called_once()
        mock_scraper.scrape_recs.assert_called_once()
        mock_searcher.search_for_recs.assert_called_once()
        # the run is marked COMPLETED at the end
        assert any(call.kwargs.get("status") == ScraperRunStatus.COMPLETED for call in mock_update_run.call_args_list)


def test_run_lfm_scraper_progress_and_completion(valid_app_settings: AppSettings) -> None:
    """The core run reports stage transitions + per-rec progress, then marks the run COMPLETED."""
    mock_scraper = MagicMock(spec=LFMRecsScraper)
    mock_scraper.scrape_recs.return_value = {EntityType.ALBUM: [object(), object()], EntityType.TRACK: [object()]}
    mock_searcher = MagicMock(spec=ReleaseSearcher)

    def _search(entity_to_recs_list: Any, snatch_override: Any, progress_callback: Any) -> None:
        for _ in range(3):  # 3 recs total
            progress_callback()

    mock_searcher.search_for_recs.side_effect = _search
    with (
        patch.object(LFMRecsScraper, "__enter__", return_value=mock_scraper),
        patch("plastered.actions.common_actions.update_scraper_run") as mock_update_run,
    ):
        run_lfm_scraper(
            app_settings=valid_app_settings,
            release_searcher=mock_searcher,
            run_id=7,
            rec_types_to_scrape_override=None,
            snatch_enabled=True,
        )
    calls = mock_update_run.call_args_list
    assert calls[0].kwargs.get("stage") == "scraping"
    searching_call = next(c for c in calls if c.kwargs.get("stage") == "searching")
    assert searching_call.kwargs.get("progress_total") == 3 and searching_call.kwargs.get("total_recs") == 3
    progress_values = [c.kwargs.get("progress_current") for c in calls if "progress_current" in c.kwargs]
    assert progress_values[-3:] == [1, 2, 3]
    assert calls[-1].kwargs.get("status") == ScraperRunStatus.COMPLETED


def test_run_lfm_scraper_marks_failed_on_error(valid_app_settings: AppSettings) -> None:
    mock_scraper = MagicMock(spec=LFMRecsScraper)
    mock_scraper.scrape_recs.side_effect = RuntimeError("boom")
    with (
        patch.object(LFMRecsScraper, "__enter__", return_value=mock_scraper),
        patch("plastered.actions.common_actions.update_scraper_run") as mock_update_run,
        pytest.raises(RuntimeError, match="boom"),
    ):
        run_lfm_scraper(
            app_settings=valid_app_settings,
            release_searcher=MagicMock(spec=ReleaseSearcher),
            run_id=7,
            rec_types_to_scrape_override=None,
            snatch_enabled=False,
        )
    assert any(call.kwargs.get("status") == ScraperRunStatus.FAILED for call in mock_update_run.call_args_list)
