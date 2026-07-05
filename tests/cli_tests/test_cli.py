from typing import Generator
from unittest.mock import MagicMock, patch, ANY

import pytest
from click.testing import CliRunner

from plastered.cli import cli
from plastered.config.app_settings import AppSettings


@pytest.fixture(scope="function")
def mock_logger_set_level() -> Generator[MagicMock, None, None]:
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


@pytest.mark.parametrize("rec_types", ["album", "track", "@all"])
def test_cli_scrape_command(valid_config_filepath: str, valid_app_settings: AppSettings, rec_types: str) -> None:
    test_cmd = ["scrape", "--rec-types", rec_types]
    with patch("plastered.cli.scrape_action", return_value=None) as mock_scrape_action_fn:
        cli_runner = CliRunner()
        result = cli_runner.invoke(cli, test_cmd)
        assert result.exit_code == 0, (
            f"Expected cli command '{' '.join(test_cmd)}' to pass but errored: {result.exception}"
        )
        mock_scrape_action_fn.assert_called_once()


@pytest.mark.parametrize(
    "cache_arg, empty_flag_present, check_flag_present, list_flag_present, read_value",
    [
        ("scraper", False, False, False, None),
        ("scraper", True, False, False, None),
        ("@all", False, False, False, None),
        ("@all", True, False, False, None),
        ("@all", False, True, False, None),
        ("scraper", False, False, True, None),
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
