"""
Expected Python version: 3.13 (with requirements.txt installed)

USAGE: See docs/user_guide.md
"""

import logging
import os
from typing import Optional

import click
from rich.console import Console

# https://stackoverflow.com/a/68878216
from rich.logging import RichHandler

from plastered.config.config_parser import AppConfig, load_init_config_template
from plastered.config.config_schema import ENABLE_SNATCHING_KEY, REC_TYPES_TO_SCRAPE_KEY
from plastered.release_search.release_searcher import ReleaseSearcher
from plastered.run_cache.run_cache import CacheType, RunCache
from plastered.scraper.lfm_scraper import LFMRecsScraper, RecommendationType
from plastered.utils.cli_utils import (
    DEFAULT_VERBOSITY,
    config_path_option,
    subcommand_flag,
)
from plastered.utils.constants import CACHE_TYPE_API, CACHE_TYPE_SCRAPER
from plastered.utils.exceptions import RunCacheDisabledException
from plastered.version import get_project_version

_TERMINAL_COLS = int(os.getenv("COLUMNS", 120))

# RichHandler(log_time_format="%m/%d/%Y %H:%M:%S")
FORMAT = "%(message)s"
logging.basicConfig(
    level="NOTSET",
    format=FORMAT,
    datefmt="[%m/%d/%Y %H:%M:%S]",
    handlers=[
        RichHandler(
            console=Console(width=_TERMINAL_COLS),
            log_time_format="%m/%d/%Y %H:%M:%S",
            omit_repeated_times=False,
            tracebacks_word_wrap=False,
        )
    ],
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
    help="plastered: Finds your LFM recs and snatches them from RED.",
)
@click.version_option(
    version=_APP_VERSION,
    package_name="plastered",
    prog_name="plastered",
)
@click.option(
    "-v",
    "--verbosity",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default=DEFAULT_VERBOSITY,
    show_default=True,
    help="Sets the logging level.",
)
@click.option("--red-user-id", type=click.INT, required=False, show_envvar=True)
@click.option("--red-api-key", type=click.STRING, required=False, show_envvar=True)
@click.option("--lfm-api-key", type=click.STRING, required=False, show_envvar=True)
@click.option("--lfm-username", type=click.STRING, required=False, show_envvar=True)
@click.option("--lfm-password", type=click.STRING, required=False, show_envvar=True)
@click.pass_context
def cli(
    ctx,
    verbosity: Optional[str] = DEFAULT_VERBOSITY,
    red_user_id: Optional[int] = None,
    red_api_key: Optional[str] = None,
    lfm_api_key: Optional[str] = None,
    lfm_username: Optional[str] = None,
    lfm_password: Optional[str] = None,
) -> None:
    _LOGGER.setLevel(verbosity.upper())
    _LOGGER.debug(f"Detected terminal width: {_TERMINAL_COLS}")
    ctx.obj = {}
    ctx.obj[_GROUP_PARAMS_KEY] = ctx.params


@cli.command(
    help="Run the app to pull LFM recs and snatch them from RED, per the settings of your config.yaml along with any CLI overrides you provide.",
    short_help="Run the app to pull LFM recs and search for / snatch them from RED.",
)
@config_path_option
@subcommand_flag(
    "--no-snatch", help_msg="When present, disables downloading the .torrent files matched to your LFM recs results."
)
@click.option(
    "-r",
    "--rec-types",
    type=click.Choice(["album", "track", "@all"], case_sensitive=False),
    required=False,
    envvar=None,
    help="Indicate what type of LFM recs to scrape and snatch. Defaults to 'rec_types_to_scrape' config setting otherwise.",
)
@click.pass_context
def scrape(ctx, config: str, no_snatch: Optional[bool] = False, rec_types: Optional[str] = None) -> None:
    if no_snatch:  # pragma: no cover
        ctx.obj[_GROUP_PARAMS_KEY][ENABLE_SNATCHING_KEY] = False
    if rec_types:
        ctx.obj[_GROUP_PARAMS_KEY][REC_TYPES_TO_SCRAPE_KEY] = (
            [rec_type.value for rec_type in RecommendationType] if rec_types == "@all" else [rec_types]
        )
    app_config = AppConfig(config_filepath=config, cli_params=ctx.obj[_GROUP_PARAMS_KEY])
    with LFMRecsScraper(app_config=app_config) as scraper:
        rec_types_to_recs_list = scraper.scrape_recs()
    release_searcher = ReleaseSearcher(app_config=app_config)
    release_searcher.search_for_recs(rec_type_to_recs_list=rec_types_to_recs_list)
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
    help="Helper command to inspect or empty the local run cache(s). See this docs page for more info on the run cache: https://github.com/windexvalence/plastered/blob/main/docs/configuration_reference.md",
    short_help="Helper command to inspect or empty the local run cache(s).",
)
@config_path_option
@subcommand_flag("--info", help_msg="Print meta-info about the disk cache(s).")
@subcommand_flag("--empty", help_msg="When present, clear cache specified by the command argument.")
@subcommand_flag("--check", help_msg="Verify / try to fix diskcache consistency for specified cache argument.")
@click.argument(
    "target_cache", envvar=None, type=click.Choice([CACHE_TYPE_API, CACHE_TYPE_SCRAPER, _CLI_ALL_CACHE_TYPES])
)
@click.pass_context
def cache(
    ctx,
    config: str,
    target_cache: str,
    info: Optional[bool] = False,
    empty: Optional[str] = False,
    check: Optional[str] = False,
) -> None:
    app_config = AppConfig(config_filepath=config, cli_params=ctx.obj[_GROUP_PARAMS_KEY])
    target_cache_types = (
        [cache_type for cache_type in CacheType] if target_cache == _CLI_ALL_CACHE_TYPES else [CacheType(target_cache)]
    )
    for target_cache_type in target_cache_types:
        target_run_cache = RunCache(app_config=app_config, cache_type=target_cache_type)
        try:
            if info:
                target_run_cache.print_summary_info()
            if empty:
                target_run_cache.clear()
            if check:
                target_run_cache.check()
        except RunCacheDisabledException:
            _LOGGER.error(
                f"{target_cache_type} cache is not enabled. To enable it, set enable_{target_cache_type}_cache to true in config.yaml."
            )
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
