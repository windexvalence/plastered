import logging
from typing import Any, Dict, List
from unittest.mock import MagicMock, call, patch

import pytest
from click.testing import CliRunner

from plastered.cli import cli
from plastered.config.config_parser import AppConfig
from plastered.release_search.release_searcher import ReleaseSearcher
from plastered.run_cache.run_cache import CacheType, RunCache
from plastered.scraper.lfm_scraper import (
    LFMRec,
    LFMRecsScraper,
    RecContext,
    RecommendationType,
)
from plastered.utils.exceptions import RunCacheDisabledException
from tests.conftest import (
    api_run_cache,
    scraper_run_cache,
    valid_app_config,
    valid_config_filepath,
)

_LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="function")
def mock_api_run_cache_instance() -> MagicMock:
    mock_api_instance = MagicMock()
    mock_api_instance.print_summary_info.return_value = None
    mock_api_instance.clear.return_value = 69
    mock_api_instance.check.return_value = "fake warning"
    mock_api_instance.close.return_value = None
    return mock_api_instance


@pytest.fixture(scope="function")
def mock_scraper_run_cache_instance() -> MagicMock:
    mock_scraper_instance = MagicMock()
    mock_scraper_instance.print_summary_info.return_value = None
    mock_scraper_instance.clear.return_value = 420
    mock_scraper_instance.check.return_value = "fake warning"
    mock_scraper_instance.close.return_value = None
    return mock_scraper_instance


@pytest.fixture(scope="function")
def mock_logger_set_level() -> MagicMock:
    with patch("plastered.cli._LOGGER.setLevel") as mock_logger_set_level:
        mock_logger_set_level.return_value = None
        yield mock_logger_set_level


@pytest.mark.parametrize("verbosity", ["DEBUG", "INFO", "WARNING", "ERROR"])
def test_cli_help_command(verbosity: str) -> None:
    with patch("plastered.cli._LOGGER.setLevel") as mock_logger_set_level:
        mock_logger_set_level.return_value = None
        cli_runner = CliRunner()
        result = cli_runner.invoke(cli, ["--help"])
        assert result.exit_code == 0, f"Expected cli command with --help flag to pass, but errored: {result.exception}"


@pytest.mark.parametrize("verbosity", ["DEBUG", "INFO", "WARNING", "ERROR"])
def test_cli_conf_command(valid_config_filepath: str, mock_logger_set_level: MagicMock, verbosity: bool) -> None:
    with patch.object(AppConfig, "pretty_print_config") as mock_pretty_print_config:
        cli_runner = CliRunner()
        cmd = ["--verbosity", verbosity, "conf", "--config", valid_config_filepath]
        result = cli_runner.invoke(cli, cmd)
        assert result.exit_code == 0, f"Expected cli command 'conf' to pass but errored: {result.exception}"
        mock_pretty_print_config.assert_called_once()
        mock_logger_set_level.assert_called_once_with(verbosity)


@pytest.mark.parametrize(
    "rec_types, mock_scrape_result",
    [
        (
            "album",
            {
                RecommendationType.ALBUM: [
                    LFMRec("Fake+Artist", "Fake+Album", RecommendationType.ALBUM, RecContext.SIMILAR_ARTIST),
                    LFMRec(
                        "Other+Fake+Artist", "Other+Fake+Album", RecommendationType.ALBUM, RecContext.SIMILAR_ARTIST
                    ),
                ],
            },
        ),
        (
            "track",
            {
                RecommendationType.TRACK: [
                    LFMRec("Even+More+Fake+Artist", "Faker+Track", RecommendationType.TRACK, RecContext.SIMILAR_ARTIST),
                    LFMRec(
                        "Other+Faker+Artist", "Faker+Shittier+Track", RecommendationType.TRACK, RecContext.IN_LIBRARY
                    ),
                ],
            },
        ),
        (
            "@all",
            {
                RecommendationType.ALBUM: [
                    LFMRec("Fake+Artist", "Fake+Album", RecommendationType.ALBUM, RecContext.SIMILAR_ARTIST),
                    LFMRec(
                        "Other+Fake+Artist", "Other+Fake+Album", RecommendationType.ALBUM, RecContext.SIMILAR_ARTIST
                    ),
                ],
                RecommendationType.TRACK: [
                    LFMRec("Even+More+Fake+Artist", "Faker+Track", RecommendationType.TRACK, RecContext.SIMILAR_ARTIST),
                    LFMRec(
                        "Other+Faker+Artist", "Faker+Shittier+Track", RecommendationType.TRACK, RecContext.IN_LIBRARY
                    ),
                ],
            },
        ),
    ],
)
def test_cli_scrape_command(
    valid_config_filepath: str,
    valid_app_config: AppConfig,
    rec_types: str,
    mock_scrape_result: Dict[RecommendationType, List[LFMRec]],
) -> None:
    with patch.object(LFMRecsScraper, "__enter__") as mock_enter:
        mock_enter.return_value = LFMRecsScraper(app_config=valid_app_config)
        with patch.object(LFMRecsScraper, "scrape_recs") as mock_scrape_recs:
            mock_scrape_recs.return_value = mock_scrape_result
            with patch.object(LFMRecsScraper, "__exit__") as mock_exit:
                with patch.object(ReleaseSearcher, "search_for_recs") as mock_search_for_recs:
                    cli_runner = CliRunner()
                    result = cli_runner.invoke(
                        cli, ["scrape", "--config", valid_config_filepath, "--rec-types", rec_types]
                    )
                    assert (
                        result.exit_code == 0
                    ), f"Expected cli command 'scrape' to pass but errored: {result.exception}"
                    mock_enter.assert_called_once()
                    mock_scrape_recs.assert_called_once()
                    mock_exit.assert_called_once()
                    mock_search_for_recs.assert_called_once_with(rec_type_to_recs_list=mock_scrape_recs.return_value)


@pytest.mark.parametrize(
    "cache_arg, info_flag_present, empty_flag_present, check_flag_present, expected_run_cache_calls",
    [
        ("api", False, False, False, [call.close()]),
        ("api", False, True, False, [call.clear(), call.close()]),
        ("api", True, False, False, [call.print_summary_info(), call.close()]),
        ("api", True, True, False, [call.print_summary_info(), call.clear(), call.close()]),
        ("scraper", False, False, False, [call.close()]),
        ("scraper", False, True, False, [call.clear(), call.close()]),
        ("scraper", True, False, False, [call.print_summary_info(), call.close()]),
        ("scraper", True, True, False, [call.print_summary_info(), call.clear(), call.close()]),
        ("@all", False, False, False, [call.close()]),
        ("@all", False, True, False, [call.clear(), call.close()]),
        ("@all", True, False, False, [call.print_summary_info(), call.close()]),
        ("@all", True, True, False, [call.print_summary_info(), call.clear(), call.close()]),
        ("@all", False, False, True, [call.check(), call.close()]),
    ],
)
def test_cli_cache_command(
    valid_config_filepath: str,
    mock_api_run_cache_instance: MagicMock,
    mock_scraper_run_cache_instance: MagicMock,
    cache_arg: str,
    info_flag_present: bool,
    empty_flag_present: bool,
    check_flag_present: bool,
    expected_run_cache_calls: List[Any],
) -> None:
    test_cmd = ["cache", "--config", valid_config_filepath, cache_arg]
    if info_flag_present:
        test_cmd.append("--info")
    if empty_flag_present:
        test_cmd.append("--empty")
    if check_flag_present:
        test_cmd.append("--check")

    def _mock_run_cache_init_side_effect(*args, **kwargs) -> RunCache:
        if kwargs["cache_type"] == "api":
            return mock_api_run_cache_instance
        if kwargs["cache_type"] == "scraper":
            return mock_scraper_run_cache_instance

    with patch("plastered.cli.RunCache") as mock_run_cache_constructor:
        mock_run_cache_constructor.side_effect = _mock_run_cache_init_side_effect
        cli_runner = CliRunner()
        result = cli_runner.invoke(cli, test_cmd)
        assert (
            result.exit_code == 0
        ), f"Expected cli command '{' '.join(test_cmd)}' to pass but errored: {result.exception}"
        if cache_arg == "api":
            mock_api_run_cache_instance.assert_has_calls(expected_run_cache_calls)
        elif cache_arg == "scraper":
            mock_scraper_run_cache_instance.assert_has_calls(expected_run_cache_calls)
        elif cache_arg == "@all":
            mock_api_run_cache_instance.assert_has_calls(expected_run_cache_calls)
            mock_scraper_run_cache_instance.assert_has_calls(expected_run_cache_calls)


def test_cli_cache_disabled_exception(
    valid_config_filepath: str,
    mock_api_run_cache_instance: MagicMock,
    mock_scraper_run_cache_instance: MagicMock,
) -> None:
    cli_runner = CliRunner()
    mock_api_run_cache_instance.check.side_effect = RunCacheDisabledException("")
    mock_scraper_run_cache_instance.check.side_effect = RunCacheDisabledException("")

    def _mock_run_cache_init_side_effect(*args, **kwargs) -> RunCache:
        if kwargs["cache_type"] == "api":
            return mock_api_run_cache_instance
        if kwargs["cache_type"] == "scraper":
            return mock_scraper_run_cache_instance

    with patch("plastered.cli.RunCache") as mock_run_cache_constructor:
        mock_run_cache_constructor.side_effect = _mock_run_cache_init_side_effect
        result = cli_runner.invoke(cli, ["cache", "--config", valid_config_filepath, "--check", "@all"])
        assert result.exit_code != 0


def test_cli_init_conf_command() -> None:
    with patch("plastered.cli.load_init_config_template") as mock_load_init_config_template:
        mock_load_init_config_template.return_value = ""
        cli_runner = CliRunner()
        result = cli_runner.invoke(cli, ["init-conf"])
        assert result.exit_code == 0, f"Expected cli command with --help flag to pass, but errored: {result.exception}"
        mock_load_init_config_template.assert_called_once()
