from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

import pytest
from click.testing import CliRunner

from plastered.cli import cli
from plastered.config.app_settings import AppSettings
from plastered.models.lfm_models import LFMRec
from plastered.models.types import RecContext, EntityType
from plastered.release_search.release_searcher import ReleaseSearcher
from plastered.scraper.lfm_scraper import LFMRecsScraper
from plastered.utils.constants import RUN_DATE_STR_FORMAT


@pytest.fixture(scope="function")
def mock_api_run_cache_instance() -> MagicMock:
    mock_api_instance = MagicMock()
    mock_api_instance.clear.return_value = 69
    mock_api_instance.check.return_value = "fake warning"
    mock_api_instance.close.return_value = None
    return mock_api_instance


@pytest.fixture(scope="function")
def mock_scraper_run_cache_instance() -> MagicMock:
    mock_scraper_instance = MagicMock()
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
                    LFMRec("Other+Fake+Artist", "Other+Fake+Album", EntityType.ALBUM, RecContext.SIMILAR_ARTIST),
                ]
            },
        ),
        (
            "track",
            {
                EntityType.TRACK: [
                    LFMRec("Even+More+Fake+Artist", "Faker+Track", EntityType.TRACK, RecContext.SIMILAR_ARTIST),
                    LFMRec("Other+Faker+Artist", "Faker+Shittier+Track", EntityType.TRACK, RecContext.IN_LIBRARY),
                ]
            },
        ),
        (
            "@all",
            {
                EntityType.ALBUM: [
                    LFMRec("Fake+Artist", "Fake+Album", EntityType.ALBUM, RecContext.SIMILAR_ARTIST),
                    LFMRec("Other+Fake+Artist", "Other+Fake+Album", EntityType.ALBUM, RecContext.SIMILAR_ARTIST),
                ],
                EntityType.TRACK: [
                    LFMRec("Even+More+Fake+Artist", "Faker+Track", EntityType.TRACK, RecContext.SIMILAR_ARTIST),
                    LFMRec("Other+Faker+Artist", "Faker+Shittier+Track", EntityType.TRACK, RecContext.IN_LIBRARY),
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
    "cache_arg, empty_flag_present, check_flag_present, list_flag_present, read_value",
    [
        ("api", False, False, False, None),
        ("api", True, False, False, None),
        ("api", False, False, False, None),
        ("api", True, False, False, None),
        ("scraper", False, False, False, None),
        ("scraper", True, False, False, None),
        ("scraper", False, False, False, None),
        ("scraper", True, False, False, None),
        ("@all", False, False, False, None),
        ("@all", True, False, False, None),
        ("@all", False, False, False, None),
        ("@all", True, False, False, None),
        ("@all", False, True, False, None),
        ("api", False, False, True, None),
        ("scraper", False, False, True, None),
        ("api", False, False, False, "false-key"),
        ("scraper", False, False, False, "false-key"),
    ],
)
def test_cli_cache_command(
    valid_config_filepath: str,
    cache_arg: str,
    empty_flag_present: bool,
    check_flag_present: bool,
    list_flag_present: bool,
    read_value: str | None,
) -> None:
    test_cmd = ["cache", "--config", valid_config_filepath, cache_arg]
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
