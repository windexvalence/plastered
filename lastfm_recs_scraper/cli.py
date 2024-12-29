"""
This script is meant to pull the relevant album / track recommendations from last.fm since their API does not directly 
surface that information. Once the proper artists + album/track details are pulled via this scraper, they can subsequently be 
used by the lastfm_recs_to_mbid.sh script to get the corresponding musicbrainz IDs and then those may be used with Lidarr auto-snatching.

Expected Python version: 3.13 (with requirements.txt installed)

USAGE: ./lastfm_recs_scraper.py
"""

from typing import List, Optional

import click

from lastfm_recs_scraper.config.config_parser import AppConfig
from lastfm_recs_scraper.release_search.release_searcher import ReleaseSearcher
from lastfm_recs_scraper.scraper.lastfm_recs_scraper import (
    LastFMRecsScraper,
    RecommendationType,
)
from lastfm_recs_scraper.utils.logging_utils import get_custom_logger

_LOGGER = get_custom_logger(__name__)


# TODO: setup yaml config as described here: https://stackoverflow.com/a/73669230
@click.group()
@click.option(
    "-c",
    "--config",
    required=True,
    type=click.Path(exists=True),
    help="Path to the application config yaml file.",
)
@click.option(
    "--output-summary-filepath",
    required=False,
    type=click.Path(),
    help="Path to write an output summary tsv file of the matched search results.",
)
@click.option("--red-api-key", required=False, envvar="RED_API_KEY")
@click.option("--last-fm-api-key", required=False, envvar="LAST_FM_API_KEY")
@click.option("--last-fm-username", required=False, envvar="LAST_FM_USERNAME")
@click.option("--last-fm-password", required=False, envvar="LAST_FM_PASSWORD")
@click.pass_context
def cli(
    ctx,
    config: str,
    output_summary_filepath: Optional[str] = None,
    red_api_key: Optional[str] = None,
    last_fm_api_key: Optional[str] = None,
    last_fm_username: Optional[str] = None,
    last_fm_password: Optional[str] = None,
) -> None:
    ctx.obj = {}
    app_config = AppConfig(config_filepath=config, cli_params=ctx.params)
    ctx.obj["app_config"] = app_config


@cli.command()
@click.pass_context
def scrape(ctx) -> None:
    app_config: AppConfig = ctx.obj["app_config"]
    with LastFMRecsScraper(app_config=app_config) as scraper:
        album_recs_list = scraper.scrape_recs_list(RecommendationType=RecommendationType.ALBUM)
        track_recs_list = scraper.scrape_recs_list(RecommendationType=RecommendationType.TRACK)
    release_searcher = ReleaseSearcher(app_config=app_config)
    release_searcher.search_for_album_recs(album_recs=album_recs_list)
    # TODO: add logic for when snatch_reqs == True


@cli.command()
@click.pass_context
def config(ctx) -> None:
    app_config: AppConfig = ctx.obj["app_config"]
    app_config.pretty_print_config()
    app_config.pretty_print_preference_ordering()


if __name__ == "__main__":
    cli()
