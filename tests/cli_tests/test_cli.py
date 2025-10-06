from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch, ANY

import pytest
from click.testing import CliRunner

from plastered.cli import cli
from plastered.config.app_settings import AppSettings
from plastered.models.lfm_models import LFMRec
from plastered.models.types import RecContext, EntityType
from plastered.release_search.release_searcher import ReleaseSearcher
from plastered.run_cache.run_cache import RunCache
from plastered.scraper.lfm_scraper import LFMRecsScraper
from plastered.utils.cli_utils import StatsRunPicker
from plastered.utils.constants import RUN_DATE_STR_FORMAT
from plastered.utils.exceptions import RunCacheDisabledException, StatsRunPickerException


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
    with patch("plastered.cli.show_config_action") as mock_show_config_action_fn:
        cli_runner = CliRunner()
        cmd = ["--verbosity", verbosity, "conf", "--config", valid_config_filepath]
        result = cli_runner.invoke(cli, cmd)
        assert result.exit_code == 0, f"Expected cli command 'conf' to pass but errored: {result.exception}"
        mock_show_config_action_fn.assert_called_once()
        mock_logger_set_level.assert_called_once_with(verbosity)


@pytest.mark.parametrize(
    "rec_types, mock_scrape_result",
    [
        (
            "album",
            {
                EntityType.ALBUM: [
                    LFMRec("Fake+Artist", "Fake+Album", EntityType.ALBUM, RecContext.SIMILAR_ARTIST),
                    LFMRec(
                        "Other+Fake+Artist", "Other+Fake+Album", EntityType.ALBUM, RecContext.SIMILAR_ARTIST
                    ),
                ]
            },
        ),
        (
            "track",
            {
                EntityType.TRACK: [
                    LFMRec("Even+More+Fake+Artist", "Faker+Track", EntityType.TRACK, RecContext.SIMILAR_ARTIST),
                    LFMRec(
                        "Other+Faker+Artist", "Faker+Shittier+Track", EntityType.TRACK, RecContext.IN_LIBRARY
                    ),
                ]
            },
        ),
        (
            "@all",
            {
                EntityType.ALBUM: [
                    LFMRec("Fake+Artist", "Fake+Album", EntityType.ALBUM, RecContext.SIMILAR_ARTIST),
                    LFMRec(
                        "Other+Fake+Artist", "Other+Fake+Album", EntityType.ALBUM, RecContext.SIMILAR_ARTIST
                    ),
                ],
                EntityType.TRACK: [
                    LFMRec("Even+More+Fake+Artist", "Faker+Track", EntityType.TRACK, RecContext.SIMILAR_ARTIST),
                    LFMRec(
                        "Other+Faker+Artist", "Faker+Shittier+Track", EntityType.TRACK, RecContext.IN_LIBRARY
                    ),
                ],
            },
        ),
    ],
)
def test_cli_scrape_command(
    valid_config_filepath: str,
    valid_app_settings: AppSettings,
    rec_types: str,
    mock_scrape_result: dict[EntityType, list[LFMRec]],
) -> None:
    with patch.object(LFMRecsScraper, "__enter__") as mock_enter:
        mock_enter.return_value = LFMRecsScraper(app_settings=valid_app_settings)
        with patch.object(LFMRecsScraper, "scrape_recs") as mock_scrape_recs:
            mock_scrape_recs.return_value = mock_scrape_result
            with patch.object(LFMRecsScraper, "__exit__") as mock_exit:
                with patch.object(ReleaseSearcher, "search_for_recs") as mock_search_for_recs:
                    cli_runner = CliRunner()
                    result = cli_runner.invoke(
                        cli, ["scrape", "--config", valid_config_filepath, "--rec-types", rec_types]
                    )
                    assert result.exit_code == 0, (
                        f"Expected cli command 'scrape' to pass but errored: {result.exception}"
                    )
                    mock_enter.assert_called_once()
                    mock_scrape_recs.assert_called_once()
                    mock_exit.assert_called_once()
                    mock_search_for_recs.assert_called_once_with(rec_type_to_recs_list=mock_scrape_recs.return_value)


@pytest.mark.parametrize(
    "cache_arg, info_flag_present, empty_flag_present, check_flag_present, list_flag_present, read_value",
    [
        ("api", False, False, False, False, None),
        ("api", False, True, False, False, None),
        ("api", True, False, False, False, None),
        ("api", True, True, False, False, None),
        ("scraper", False, False, False, False, None),
        ("scraper", False, True, False, False, None),
        ("scraper", True, False, False, False, None),
        ("scraper", True, True, False, False, None),
        ("@all", False, False, False, False, None),
        ("@all", False, True, False, False, None),
        ("@all", True, False, False, False, None),
        ("@all", True, True, False, False, None),
        ("@all", False, False, True, False, None),
        ("api", False, False, False, True, None),
        ("scraper", False, False, False, True, None),
        ("api", False, False, False, False, "false-key"),
        (
            "scraper",
            False,
            False,
            False,
            False,
            "false-key",
        ),
    ],
)
def test_cli_cache_command(
    valid_config_filepath: str,
    cache_arg: str,
    info_flag_present: bool,
    empty_flag_present: bool,
    check_flag_present: bool,
    list_flag_present: bool,
    read_value: str | None,
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
    
    with patch("plastered.cli.cache_action", return_value=None) as mock_cache_action_fn:
        cli_runner = CliRunner()
        result = cli_runner.invoke(cli, test_cmd)
        assert result.exit_code == 0, (
            f"Expected cli command '{' '.join(test_cmd)}' to pass but errored: {result.exception}"
        )
        mock_cache_action_fn.assert_called_once_with(
            app_settings=ANY,
            target_cache=cache_arg,
            info=info_flag_present,
            empty=empty_flag_present,
            check=check_flag_present,
            list_keys=list_flag_present,
            read_value=read_value,
        )


def test_cli_init_conf_command() -> None:
    with patch("plastered.cli.load_init_config_template") as mock_load_init_config_template:
        mock_load_init_config_template.return_value = ""
        cli_runner = CliRunner()
        result = cli_runner.invoke(cli, ["init-conf"])
        assert result.exit_code == 0, f"Expected cli command with --help flag to pass, but errored: {result.exception}"
        mock_load_init_config_template.assert_called_once()


@pytest.mark.parametrize("run_date_provided", [False, True])
def test_cli_inspect_stats_command(
    mock_output_summary_dir_path: Path, valid_config_filepath_function_scoped: str, run_date_provided: bool
) -> None:
    mocked_run_date_str = "2025-01-20__00-24-42"
    test_cmd = ["inspect-stats", "--config", valid_config_filepath_function_scoped]
    if run_date_provided:
        test_cmd.extend(["--run-date", mocked_run_date_str])
    with (
        patch.object(
            AppSettings, "get_root_summary_directory_path", return_value=str(mock_output_summary_dir_path)
        ) as mock_app_conf_get_root_summary_dir_path,
        patch(
            "plastered.cli.prompt_user_for_run_date",
            return_value=datetime.strptime(mocked_run_date_str, RUN_DATE_STR_FORMAT),
        ) as mock_srp_get_run_date,
        patch("plastered.cli.PriorRunStats") as mock_prior_run_stats_constructor,
    ):
        mock_prs_instance = MagicMock()
        mock_prior_run_stats_constructor.return_value = mock_prs_instance
        mock_prs_instance.print_summary_tables.return_value = None
        cli_runner = CliRunner()
        result = cli_runner.invoke(cli, test_cmd)
        assert result.exit_code == 0
        mock_prior_run_stats_constructor.assert_called_once()
        mock_prs_instance.print_summary_tables.assert_called_once()


def test_cli_inspect_stats_command_exception(valid_config_filepath: str, mock_run_date_str: str) -> None:
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
