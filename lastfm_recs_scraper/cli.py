"""
This script is meant to pull the relevant album / track recommendations from last.fm since their API does not directly 
surface that information. Once the proper artists + album/track details are pulled via this scraper, they can subsequently be 
used by the lastfm_recs_to_mbid.sh script to get the corresponding musicbrainz IDs and then those may be used with Lidarr auto-snatching.

Expected Python version: 3.13 (with requirements.txt installed)

USAGE: ./lastfm_recs_scraper.py
"""

from typing import Optional

import click

from lastfm_recs_scraper.config.config_parser import (
    AppConfig,
    load_init_config_template,
)
from lastfm_recs_scraper.release_search.release_searcher import ReleaseSearcher
from lastfm_recs_scraper.run_cache.run_cache import CacheType, RunCache
from lastfm_recs_scraper.scraper.last_scraper import (
    LastFMRecsScraper,
    RecommendationType,
)
from lastfm_recs_scraper.utils.constants import CACHE_TYPE_API, CACHE_TYPE_SCRAPER
from lastfm_recs_scraper.utils.logging_utils import get_custom_logger

_LOGGER = get_custom_logger(__name__)

_GROUP_PARAMS_KEY = "group_params"
_CLI_ALL_CACHE_TYPES = "@all"

# TODO: dynamically pull version number from build_scripts/release-tag.txt for the version option


# pylint: disable=unused-argument,too-many-arguments,no-value-for-parameter
@click.group()
@click.version_option(
    version="0.0.1-beta",
    package_name="last-red-recs",
    prog_name="last-red-recs",
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
    output_summary_filepath: Optional[str] = None,
    red_api_key: Optional[str] = None,
    last_fm_api_key: Optional[str] = None,
    last_fm_username: Optional[str] = None,
    last_fm_password: Optional[str] = None,
) -> None:
    ctx.obj = {}
    ctx.obj[_GROUP_PARAMS_KEY] = ctx.params


@cli.command(
    help="Run the app to pull LFM recs and snatch them from RED, per the settings of your config.yaml along with any CLI overrides you provide.",
    short_help="Run the app to pull LFM recs and snatch them from RED.",
)
@click.pass_context
@click.option(
    "-c", "--config", required=True, type=click.Path(exists=True), help="Path to the application config yaml file."
)
def scrape(ctx, config: str) -> None:
    app_config = AppConfig(config_filepath=config, cli_params=ctx.obj[_GROUP_PARAMS_KEY])
    with LastFMRecsScraper(app_config=app_config) as scraper:
        album_recs_list = scraper.scrape_recs_list(recommendation_type=RecommendationType.ALBUM)
        # TODO (later): Enable track scraping
        # track_recs_list = scraper.scrape_recs_list(recommendation_type=RecommendationType.TRACK)
    release_searcher = ReleaseSearcher(app_config=app_config)
    release_searcher.gather_red_user_details()
    release_searcher.search_for_album_recs(album_recs=album_recs_list)


@cli.command(
    help="Output the contents of your existing config.yaml, along with any default values and/or CLI option overrides.",
    short_help="Output the current state of your app config for inspection.",
)
@click.option(
    "-c", "--config", required=True, type=click.Path(exists=True), help="Path to the application config yaml file."
)
@click.pass_context
def conf(ctx, config: str) -> None:
    app_config = AppConfig(config_filepath=config, cli_params=ctx.obj[_GROUP_PARAMS_KEY])
    app_config.pretty_print_config()
    app_config.pretty_print_preference_ordering()


@cli.command(
    help="Helper command to inspect or empty the local run cache(s). See configuration_reference.md docs page for more info on the run cache.",
    short_help="Helper command to inspect or empty the local run cache(s).",
)
@click.option(
    "-c", "--config", required=True, type=click.Path(exists=True), help="Path to the application config yaml file."
)
@click.option(
    "-k",
    "--kind",
    required=True,
    type=click.Choice([CACHE_TYPE_API, CACHE_TYPE_SCRAPER, _CLI_ALL_CACHE_TYPES]),
    help=f"Indicate the desired kind of cache type to run the command against. May set to '{_CLI_ALL_CACHE_TYPES}' to run against all cache types.",
)
@click.option("-i", "--info", is_flag=True, default=False, help="Print meta-info about the disk cache(s).")
@click.option(
    "-e",
    "--empty",
    is_flag=True,
    default=False,
    help="When flag is present, empty the cache(s) specified by the --type option.",
)
@click.pass_context
def cache(ctx, config: str, kind: str, info: Optional[bool] = False, empty: Optional[str] = None) -> None:
    app_config = AppConfig(config_filepath=config, cli_params=ctx.obj[_GROUP_PARAMS_KEY])
    target_cache_types = [cache_type for cache_type in CacheType] if kind == _CLI_ALL_CACHE_TYPES else [CacheType(kind)]
    for target_cache_type in target_cache_types:
        target_run_cache = RunCache(app_config=app_config, cache_type=target_cache_type)
        if info:
            target_run_cache.print_summary_info()
        if empty:
            num_entries_removed = target_run_cache.clear()
            _LOGGER.info(f"{target_cache_type} emptied: {num_entries_removed} entries removed.")
        target_run_cache.close()


@cli.command(
    help="Output the contents of a template starter config to aid in initial app setup. Output may be redirected to the desired config filepath on your host machine.",
    short_help="Output the contents of a starter config template for initial setup.",
)
def init_conf() -> None:
    raw_init_conf_data_str = load_init_config_template()
    print(raw_init_conf_data_str)


if __name__ == "__main__":  # pragma: no cover
    cli()
