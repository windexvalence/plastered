from traceback import format_exc

import pytest
from click.testing import CliRunner

from lastfm_recs_scraper.cli import cli
from tests.conftest import valid_config_filepath


def test_cli_help_command() -> None:
    cli_runner = CliRunner()
    result = cli_runner.invoke(cli, ["--help"])
    assert result.exit_code == 0, f"Expected cli command with --help flag to pass, but errored: {result.exception}"


# TODO: add other cli command unit test functions here
def test_cli_config_command(valid_config_filepath: str) -> None:
    cli_runner = CliRunner()
    result = cli_runner.invoke(cli, ["--config", valid_config_filepath, "config"])
    assert result.exit_code == 0, f"Expected cli command 'config' to pass but errored: {result.exception}"


def test_cli_scrape_command() -> None:
    pass  # TODO: implement
