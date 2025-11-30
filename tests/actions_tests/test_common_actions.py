from unittest.mock import MagicMock, patch

import pytest

from plastered.actions.common_actions import cache_action, scrape_action, show_config_action
from plastered.config.app_settings import AppSettings
from plastered.models.types import CacheType
from plastered.release_search.release_searcher import ReleaseSearcher
from plastered.run_cache.run_cache import RunCache
from plastered.scraper.lfm_scraper import LFMRecsScraper


@pytest.mark.parametrize("target_cache", ["api", "scraper", "all"])
@pytest.mark.parametrize(
    "test_kwargs, run_cache_method_name",
    [
        ({"empty": True}, "clear"),
        ({"check": True}, "check"),
        ({"list_keys": True}, "cli_list_cache_keys"),
        ({"read_value": "fake-key"}, "cli_print_cached_value"),
    ],
)
def test_cache_action(
    valid_app_settings: AppSettings,
    target_cache: str,
    test_kwargs: dict[str, bool | str | None],
    run_cache_method_name: str,
) -> None:
    with patch.object(RunCache, "close") as mock_close, patch.object(RunCache, run_cache_method_name) as mock_method:
        cache_action(app_settings=valid_app_settings, target_cache=target_cache, **test_kwargs)
        if target_cache != "all":
            mock_method.assert_called_once()
            mock_close.assert_called_once()
        else:
            assert len(mock_method.mock_calls) == 2
            assert len(mock_close.mock_calls) == 2


@pytest.mark.parametrize("target_cache", ["api", "scraper"])
@pytest.mark.parametrize(
    "test_kwargs", [{"empty": True}, {"check": True}, {"list_keys": True}, {"read_value": "fake-key"}]
)
def test_cache_action_disabled_raises(
    valid_app_settings: AppSettings, target_cache: str, test_kwargs: dict[str, bool | str | None]
) -> None:
    """Ensures calls to cache_action exit with a non-zero exit code when the cache is disabled."""
    with patch.object(AppSettings, "is_cache_enabled", return_value=False):
        with pytest.raises(SystemExit) as excinfo:
            cache_action(app_settings=valid_app_settings, target_cache=target_cache, **test_kwargs)
        assert excinfo.type == SystemExit
        assert excinfo.value.code == 2


def test_show_config_action(valid_app_settings: AppSettings) -> None:
    with patch.object(AppSettings, "model_dump_json", return_value='{"mock": "data"}') as mock_app_settings_model_dump:
        _ = show_config_action(app_settings=valid_app_settings)
        mock_app_settings_model_dump.assert_called_once()


def test_scrape_action(valid_app_settings: AppSettings) -> None:
    mock_scraper = MagicMock(spec=LFMRecsScraper)
    mock_searcher = MagicMock(spec=ReleaseSearcher)
    with (
        patch.object(LFMRecsScraper, "__enter__", return_value=mock_scraper) as mock_scraper_enter,
        patch.object(ReleaseSearcher, "__enter__", return_value=mock_searcher) as mock_searcher_enter,
    ):
        scrape_action(app_settings=valid_app_settings)
        mock_scraper_enter.assert_called_once()
        mock_scraper.scrape_recs.assert_called_once()
        mock_searcher_enter.assert_called_once()
        mock_searcher.search_for_recs.assert_called_once()
