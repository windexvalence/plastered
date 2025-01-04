from traceback import format_exc
from unittest.mock import call, patch

import pytest
from click.testing import CliRunner

from lastfm_recs_scraper.cli import cli
from lastfm_recs_scraper.config.config_parser import AppConfig
from lastfm_recs_scraper.release_search.release_searcher import (
    LastFMRec,
    ReleaseSearcher,
)
from lastfm_recs_scraper.scraper.lastfm_recs_scraper import (
    LastFMRecsScraper,
    RecContext,
    RecommendationType,
)
from lastfm_recs_scraper.utils.red_utils import RedUserDetails
from tests.conftest import (
    mock_red_user_details,
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
            result = cli_runner.invoke(cli, ["--config", valid_config_filepath, "conf"])
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
                        result = cli_runner.invoke(cli, ["--config", valid_config_filepath, "scrape"])
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
