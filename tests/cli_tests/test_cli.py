import logging
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest
from click.testing import CliRunner

from plastered.cli import cli
from plastered.config.config_parser import AppConfig
from plastered.release_search.release_searcher import ReleaseSearcher
from plastered.run_cache.run_cache import RunCache
from plastered.scraper.lfm_scraper import (
    LFMRec,
    LFMRecsScraper,
    RecContext,
    RecommendationType,
)
from plastered.utils.cli_utils import StatsRunPicker
from plastered.utils.constants import RUN_DATE_STR_FORMAT
from plastered.utils.exceptions import (
    RunCacheDisabledException,
    StatsRunPickerException,
)
from tests.conftest import (
    api_run_cache,
    mock_run_date_str,
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
    mock_scrape_result: dict[RecommendationType, list[LFMRec]],
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
    "cache_arg, info_flag_present, empty_flag_present, check_flag_present, list_flag_present, read_value, expected_run_cache_calls",
    [
        ("api", False, False, False, False, None, [call.close()]),
        ("api", False, True, False, False, None, [call.clear(), call.close()]),
        ("api", True, False, False, False, None, [call.print_summary_info(), call.close()]),
        ("api", True, True, False, False, None, [call.print_summary_info(), call.clear(), call.close()]),
        ("scraper", False, False, False, False, None, [call.close()]),
        ("scraper", False, True, False, False, None, [call.clear(), call.close()]),
        ("scraper", True, False, False, False, None, [call.print_summary_info(), call.close()]),
        ("scraper", True, True, False, False, None, [call.print_summary_info(), call.clear(), call.close()]),
        ("@all", False, False, False, False, None, [call.close()]),
        ("@all", False, True, False, False, None, [call.clear(), call.close()]),
        ("@all", True, False, False, False, None, [call.print_summary_info(), call.close()]),
        ("@all", True, True, False, False, None, [call.print_summary_info(), call.clear(), call.close()]),
        ("@all", False, False, True, False, None, [call.check(), call.close()]),
        ("api", False, False, False, True, None, [call.cli_list_cache_keys()]),
        ("scraper", False, False, False, True, None, [call.cli_list_cache_keys()]),
        ("api", False, False, False, False, "false-key", [call.cli_print_cached_value(key="false-key"), call.close()]),
        (
            "scraper",
            False,
            False,
            False,
            False,
            "false-key",
            [call.cli_print_cached_value(key="false-key"), call.close()],
        ),
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
    list_flag_present: bool,
    read_value: str | None,
    expected_run_cache_calls: list[Any],
) -> None:
    test_cmd = ["cache", "--config", valid_config_filepath, cache_arg]
    if info_flag_present:
        test_cmd.append("--info")
    if empty_flag_present:
        test_cmd.append("--empty")
    if check_flag_present:
        test_cmd.append("--check")
    if list_flag_present:
        test_cmd.append("--list-keys")
    if read_value:
        test_cmd.extend(["--read-value", read_value])

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


@pytest.mark.parametrize("run_date_provided", [False, True])
def test_cli_inspect_stats_command(
    valid_config_filepath: str,
    mock_run_date_str: str,
    run_date_provided: bool,
) -> None:
    test_cmd = ["inspect-stats", "--config", valid_config_filepath]
    if run_date_provided:
        test_cmd.append("--run-date")
        test_cmd.append(mock_run_date_str)
    with patch.object(StatsRunPicker, "get_run_date_from_user_prompts") as mock_srp_get_run_date:
        mock_srp_get_run_date.return_value = datetime.strptime(mock_run_date_str, RUN_DATE_STR_FORMAT)
        with patch("plastered.cli.PriorRunStats") as mock_prior_run_stats_constructor:
            mock_prs_instance = MagicMock()
            mock_prior_run_stats_constructor.return_value = mock_prs_instance
            mock_prs_instance.print_summary_tables.return_value = None
            cli_runner = CliRunner()
            result = cli_runner.invoke(cli, test_cmd)
            assert result.exit_code == 0
            mock_prior_run_stats_constructor.assert_called_once()
            mock_prs_instance.print_summary_tables.assert_called_once()


def test_cli_inspect_stats_command_exception(
    valid_config_filepath: str,
    mock_run_date_str: str,
) -> None:
    test_cmd = ["inspect-stats", "--config", valid_config_filepath]

    def _prs_side_effect(*args, **kwargs) -> None:
        raise StatsRunPickerException("No run summary directories found.")

    with patch.object(
        StatsRunPicker, "get_run_date_from_user_prompts", side_effect=_prs_side_effect
    ) as mock_srp_get_run_date:
        mock_srp_get_run_date.return_value = datetime.strptime(mock_run_date_str, RUN_DATE_STR_FORMAT)
        cli_runner = CliRunner()
        result = cli_runner.invoke(cli, test_cmd)
        assert result.exit_code != 0
