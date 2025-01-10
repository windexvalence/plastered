from traceback import format_exc
from typing import Any, List
from unittest.mock import MagicMock, call, patch

import pytest
from click.testing import CliRunner

from lastfm_recs_scraper.cli import cli
from lastfm_recs_scraper.config.config_parser import AppConfig
from lastfm_recs_scraper.release_search.release_searcher import (
    LastFMRec,
    ReleaseSearcher,
)
from lastfm_recs_scraper.run_cache.run_cache import CacheType, RunCache
from lastfm_recs_scraper.scraper.last_scraper import (
    LastFMRecsScraper,
    RecContext,
    RecommendationType,
)
from lastfm_recs_scraper.utils.red_utils import RedUserDetails
from tests.conftest import (
    api_run_cache,
    mock_red_user_details,
    scraper_run_cache,
    valid_app_config,
    valid_config_filepath,
)


def test_cli_help_command() -> None:
    cli_runner = CliRunner()
    result = cli_runner.invoke(cli, ["--help"])
    assert result.exit_code == 0, f"Expected cli command with --help flag to pass, but errored: {result.exception}"


def test_cli_conf_command(valid_config_filepath: str) -> None:
    with patch.object(AppConfig, "pretty_print_config") as mock_pretty_print_config:
        with patch.object(AppConfig, "pretty_print_preference_ordering") as mock_pretty_print_preference_ordering:
            cli_runner = CliRunner()
            result = cli_runner.invoke(cli, ["conf", "--config", valid_config_filepath])
            assert result.exit_code == 0, f"Expected cli command 'conf' to pass but errored: {result.exception}"
            mock_pretty_print_config.assert_called_once()
            mock_pretty_print_preference_ordering.assert_called_once()


def test_cli_scrape_command(
    valid_config_filepath: str, valid_app_config: AppConfig, mock_red_user_details: RedUserDetails
) -> None:
    with patch.object(LastFMRecsScraper, "__enter__") as mock_enter:
        mock_enter.return_value = LastFMRecsScraper(app_config=valid_app_config)
        with patch.object(LastFMRecsScraper, "scrape_recs_list") as mock_scrape_recs_list:
            mock_scrape_recs_list.return_value = [
                LastFMRec("Fake+Artist", "Fake+Album", RecommendationType.ALBUM, RecContext.SIMILAR_ARTIST),
                LastFMRec("Other+Fake+Artist", "Other+Fake+Album", RecommendationType.ALBUM, RecContext.SIMILAR_ARTIST),
            ]
            with patch.object(LastFMRecsScraper, "__exit__") as mock_exit:
                with patch.object(ReleaseSearcher, "search_for_album_recs") as mock_search_for_album_recs:
                    with patch.object(ReleaseSearcher, "gather_red_user_details") as mock_gather_red_user_details:
                        mock_gather_red_user_details.return_value = mock_red_user_details
                        cli_runner = CliRunner()
                        result = cli_runner.invoke(cli, ["scrape", "--config", valid_config_filepath])
                        assert (
                            result.exit_code == 0
                        ), f"Expected cli command 'scrape' to pass but errored: {result.exception}"
                        mock_enter.assert_called_once()
                        mock_scrape_recs_list.assert_has_calls(
                            [
                                call(recommendation_type=RecommendationType.ALBUM),
                                # call(recommendation_type=RecommendationType.TRACK),
                            ]
                        )
                        mock_exit.assert_called_once()
                        mock_search_for_album_recs.assert_called_once_with(
                            album_recs=mock_scrape_recs_list.return_value
                        )


@pytest.mark.parametrize(
    "kind_opt, info_flag_present, empty_flag_present, expected_run_cache_calls",
    [
        ("api", False, False, [call.close()]),
        ("api", False, True, [call.clear(), call.close()]),
        ("api", True, False, [call.print_summary_info(), call.close()]),
        ("api", True, True, [call.print_summary_info(), call.clear(), call.close()]),
        ("scraper", False, False, [call.close()]),
        ("scraper", False, True, [call.clear(), call.close()]),
        ("scraper", True, False, [call.print_summary_info(), call.close()]),
        ("scraper", True, True, [call.print_summary_info(), call.clear(), call.close()]),
        ("@all", False, False, [call.close()]),
        ("@all", False, True, [call.clear(), call.close()]),
        ("@all", True, False, [call.print_summary_info(), call.close()]),
        ("@all", True, True, [call.print_summary_info(), call.clear(), call.close()]),
    ],
)
def test_cli_cache_command(
    valid_config_filepath: str,
    kind_opt: str,
    info_flag_present: bool,
    empty_flag_present: bool,
    expected_run_cache_calls: List[Any],
) -> None:
    test_cmd = ["cache", "--config", valid_config_filepath, "--kind", kind_opt]
    if info_flag_present:
        test_cmd.append("--info")
    if empty_flag_present:
        test_cmd.append("--empty")
    mock_api_run_cache = MagicMock()
    mock_scraper_run_cache = MagicMock()

    def _mock_run_cache_init_side_effect(*args, **kwargs) -> RunCache:
        if kwargs["cache_type"] == "api":
            return mock_api_run_cache
        if kwargs["cache_type"] == "scraper":
            return mock_scraper_run_cache

    mock_api_run_cache.print_summary_info.return_value = None
    mock_api_run_cache.clear.return_value = 69
    mock_api_run_cache.close.return_value = None
    mock_scraper_run_cache.print_summary_info.return_value = None
    mock_scraper_run_cache.clear.return_value = 420
    mock_scraper_run_cache.close.return_value = None
    with patch("lastfm_recs_scraper.cli.RunCache") as mock_run_cache_constructor:
        mock_run_cache_constructor.side_effect = _mock_run_cache_init_side_effect
        cli_runner = CliRunner()
        result = cli_runner.invoke(cli, test_cmd)
        assert (
            result.exit_code == 0
        ), f"Expected cli command '{' '.join(test_cmd)}' to pass but errored: {result.exception}"
        if kind_opt == "api":
            mock_api_run_cache.assert_has_calls(expected_run_cache_calls)
        elif kind_opt == "scraper":
            mock_scraper_run_cache.assert_has_calls(expected_run_cache_calls)
        elif kind_opt == "@all":
            mock_api_run_cache.assert_has_calls(expected_run_cache_calls)
            mock_scraper_run_cache.assert_has_calls(expected_run_cache_calls)


def test_cli_init_conf_command() -> None:
    with patch("lastfm_recs_scraper.cli.load_init_config_template") as mock_load_init_config_template:
        mock_load_init_config_template.return_value = ""
        cli_runner = CliRunner()
        result = cli_runner.invoke(cli, ["init-conf"])
        assert result.exit_code == 0, f"Expected cli command with --help flag to pass, but errored: {result.exception}"
        mock_load_init_config_template.assert_called_once()
