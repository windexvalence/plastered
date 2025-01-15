"""
This script is meant to pull the relevant album / track recommendations from last.fm since their API does not directly 
surface that information. Once the proper artists + album/track details are pulled via this scraper, they can subsequently be 
used by the lastfm_recs_to_mbid.sh script to get the corresponding musicbrainz IDs and then those may be used with Lidarr auto-snatching.

Expected Python version: 3.13 (with requirements.txt installed)

USAGE: ./lastfm_recs_scraper.py
"""
from functools import wraps
import logging
from typing import Optional

# https://stackoverflow.com/a/68878216
from rich.logging import RichHandler
# from rich.theme import Theme
from rich.console import Console
import click

from lastfm_recs_scraper.version import get_project_version
from lastfm_recs_scraper.config.config_parser import (
    AppConfig,
    load_init_config_template,
)
from lastfm_recs_scraper.config.config_schema import ENABLE_SNATCHING_KEY
from lastfm_recs_scraper.release_search.release_searcher import ReleaseSearcher
from lastfm_recs_scraper.run_cache.run_cache import CacheType, RunCache
from lastfm_recs_scraper.scraper.last_scraper import (
    LastFMRecsScraper,
    RecommendationType,
)
from lastfm_recs_scraper.utils.constants import CACHE_TYPE_API, CACHE_TYPE_SCRAPER
from lastfm_recs_scraper.utils.cli_utils import config_path_option, DEFAULT_VERBOSITY, subcommand_flag
from lastfm_recs_scraper.utils.exceptions import RunCacheDisabledException

# RichHandler(log_time_format="%m/%d/%Y %H:%M:%S")
FORMAT = "%(message)s"
logging.basicConfig(
    level="NOTSET",
    format=FORMAT,
    datefmt="[%m/%d/%Y %H:%M:%S]",
    handlers=[RichHandler(
        console=Console(width=120),
        log_time_format="%m/%d/%Y %H:%M:%S",
        omit_repeated_times=False,
        tracebacks_word_wrap=False,
    )],
)  # set level=20 or logging.INFO to turn off debug
_LOGGER = logging.getLogger()
# _LOGGER = logging.getLogger("rich")

_APP_VERSION = get_project_version()

_OPTION_ENVVAR_PREFIX = "PLASTERED"
_GROUP_PARAMS_KEY = "group_params"
_CLI_ALL_CACHE_TYPES = "@all"


# pylint: disable=unused-argument,too-many-arguments,no-value-for-parameter
@click.group(
    context_settings={"auto_envvar_prefix": _OPTION_ENVVAR_PREFIX},
    help="last-red-recs: Finds your LFM recs and snatches them from RED.",
)
@click.version_option(
    version=_APP_VERSION,
    package_name="last-red-recs",
    prog_name="last-red-recs",
)
@click.option(
    "-v", "--verbosity",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default=DEFAULT_VERBOSITY,
    show_default=True,
    help="Sets the logging level.",
)
@click.option("--red-user-id", type=click.INT, required=False, show_envvar=True)
@click.option("--red-api-key", type=click.STRING, required=False, show_envvar=True)
@click.option("--last-fm-api-key", type=click.STRING, required=False, show_envvar=True)
@click.option("--last-fm-username", type=click.STRING, required=False, show_envvar=True)
@click.option("--last-fm-password", type=click.STRING, required=False, show_envvar=True)
@click.pass_context
def cli(
    ctx,
    verbosity: Optional[str] = DEFAULT_VERBOSITY,
    red_user_id: Optional[int] = None,
    red_api_key: Optional[str] = None,
    last_fm_api_key: Optional[str] = None,
    last_fm_username: Optional[str] = None,
    last_fm_password: Optional[str] = None,
) -> None:
    _LOGGER.setLevel(verbosity.upper())
    ctx.obj = {}
    ctx.obj[_GROUP_PARAMS_KEY] = ctx.params


@cli.command(
    help="Run the app to pull LFM recs and snatch them from RED, per the settings of your config.yaml along with any CLI overrides you provide.",
    short_help="Run the app to pull LFM recs and search for / snatch them from RED.",
)
@config_path_option
@subcommand_flag(
    "--no-snatch", help="When present, disables downloading the .torrent files matched to your LFM recs results."
)
@click.pass_context
def scrape(ctx, config: str, no_snatch: Optional[bool] = False) -> None:
    if no_snatch:  # pragma: no cover
        ctx.obj[_GROUP_PARAMS_KEY][ENABLE_SNATCHING_KEY] = False
    app_config = AppConfig(config_filepath=config, cli_params=ctx.obj[_GROUP_PARAMS_KEY])
    with LastFMRecsScraper(app_config=app_config) as scraper:
        album_recs_list = scraper.scrape_recs_list(recommendation_type=RecommendationType.ALBUM)
        # TODO (later): Enable track scraping
        # track_recs_list = scraper.scrape_recs_list(recommendation_type=RecommendationType.TRACK)
    release_searcher = ReleaseSearcher(app_config=app_config)
    release_searcher.gather_red_user_details()
    release_searcher.search_for_album_recs(album_recs=album_recs_list)
    release_searcher.snatch_matches()
    release_searcher.generate_summary_stats()


@cli.command(
    help="Output the contents of your existing config.yaml, along with any default values and/or CLI option overrides.",
    short_help="Output the current state of your app config for inspection.",
)
@config_path_option
@click.pass_context
def conf(ctx, config: str) -> None:
    app_config = AppConfig(config_filepath=config, cli_params=ctx.obj[_GROUP_PARAMS_KEY])
    app_config.pretty_print_config()


@cli.command(
    help="Helper command to inspect or empty the local run cache(s). See this docs page for more info on the run cache: https://github.com/windexvalence/last-red-recs/blob/main/docs/configuration_reference.md",
    short_help="Helper command to inspect or empty the local run cache(s).",
)
@config_path_option
@subcommand_flag("--info", help="Print meta-info about the disk cache(s).")
@subcommand_flag("--empty", help="When present, clear cache specified by the command argument.")
@subcommand_flag("--check", help="Verify / try to fix diskcache consistency for specified cache argument.")
@click.argument("cache", envvar=None, type=click.Choice([CACHE_TYPE_API, CACHE_TYPE_SCRAPER, _CLI_ALL_CACHE_TYPES]))
@click.pass_context
def cache(
    ctx,
    config: str,
    cache: str,
    info: Optional[bool] = False,
    empty: Optional[str] = False,
    check: Optional[str] = False,
) -> None:
    app_config = AppConfig(config_filepath=config, cli_params=ctx.obj[_GROUP_PARAMS_KEY])
    target_cache_types = [cache_type for cache_type in CacheType] if cache == _CLI_ALL_CACHE_TYPES else [CacheType(cache)]
    for target_cache_type in target_cache_types:
        target_run_cache = RunCache(app_config=app_config, cache_type=target_cache_type)
        try:
            if info:
                target_run_cache.print_summary_info()
            if empty:
                num_entries_removed = target_run_cache.clear()
                _LOGGER.info(f"{target_cache_type} emptied: {num_entries_removed} entries removed.")
            if check:
                diskcache_warnings = target_run_cache.check()
                print(f"{target_cache_type} check warnings (if any): ")
                print('\n'.join(diskcache_warnings))
        except RunCacheDisabledException:
            _LOGGER.error(f"{target_cache_type} cache is not enabled. To enable it, set enable_{target_cache_type}_cache to true in config.yaml.")
            ctx.exit(2)
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
