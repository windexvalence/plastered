"""
Expected Python version: 3.12.8

USAGE: See docs/user_guide.md
"""

import logging
from datetime import datetime
from pathlib import Path
from pprint import pprint
from typing import Final

import click

from plastered.actions import cache_action, scrape_action, show_config_action
from plastered.config.app_settings import get_app_settings, load_init_config_template
from plastered.config.field_validators import CLIOverrideSetting
from plastered.models.types import ALL_ENTITY_TYPES
from plastered.stats.stats import PriorRunStats
from plastered.utils.cli_utils import DEFAULT_VERBOSITY, config_path_option, prompt_user_for_run_date, subcommand_flag
from plastered.utils.constants import CACHE_TYPE_API, CACHE_TYPE_SCRAPER, CLI_ALL_CACHE_TYPES, RUN_DATE_STR_FORMAT
from plastered.utils.exceptions import StatsRunPickerException
from plastered.utils.log_utils import DATE_FORMAT, FORMAT, create_rich_log_handler
from plastered.version import get_project_version

logging.basicConfig(level="NOTSET", format=FORMAT, datefmt=DATE_FORMAT, handlers=[create_rich_log_handler()])
_LOGGER = logging.getLogger()

_APP_VERSION = get_project_version()
_OPTION_ENVVAR_PREFIX: Final[str] = "PLASTERED"
_GROUP_PARAMS_KEY: Final[str] = "group_params"


# pylint: disable=unused-argument,too-many-arguments,no-value-for-parameter
@click.group(
    context_settings={"auto_envvar_prefix": _OPTION_ENVVAR_PREFIX},
    help="plastered: Finds your LFM recs and snatches them from RED.",
)
@click.version_option(version=_APP_VERSION, package_name="plastered", prog_name="plastered")
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
    verbosity: str | None = DEFAULT_VERBOSITY,
    red_user_id: int | None = None,
    red_api_key: str | None = None,
    lfm_api_key: str | None = None,
    lfm_username: str | None = None,
    lfm_password: str | None = None,
) -> None:
    verbosity = verbosity or DEFAULT_VERBOSITY
    _LOGGER.setLevel(verbosity.upper())
    ctx.params.pop("verbosity", None)
    ctx.obj = {}
    # ctx.obj[_GROUP_PARAMS_KEY] =   # ctx.params
    possible_overrides = {
        CLIOverrideSetting.RED_USER_ID.name: red_user_id,
        CLIOverrideSetting.RED_API_KEY.name: red_api_key,
        CLIOverrideSetting.LFM_API_KEY.name: lfm_api_key,
        CLIOverrideSetting.LFM_USERNAME.name: lfm_username,
        CLIOverrideSetting.LFM_PASSWORD.name: lfm_password,
    }
    ctx.obj[_GROUP_PARAMS_KEY] = {k: v for k, v in possible_overrides.items() if v is not None}


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
def scrape(ctx, config: str, no_snatch: bool | None = False, rec_types: str | None = None) -> None:
    if no_snatch:  # pragma: no cover
        ctx.obj[_GROUP_PARAMS_KEY][CLIOverrideSetting.SNATCH_ENABLED.name] = False
    if rec_types:
        ctx.obj[_GROUP_PARAMS_KEY][CLIOverrideSetting.REC_TYPES.name] = (
            list(ALL_ENTITY_TYPES) if rec_types == "@all" else [rec_types]
        )
    app_settings = get_app_settings(src_yaml_filepath=Path(config), cli_overrides=ctx.obj.pop(_GROUP_PARAMS_KEY, None))
    scrape_action(app_settings=app_settings)


@cli.command(
    help="Gather and inspect the summary stats of a prior scrape run identified by the specified run_date.",
    short_help="View the summary stats of a specific past scrape run",
)
@config_path_option
@click.option(
    "-d",
    "--run-date",
    type=click.DateTime(formats=[RUN_DATE_STR_FORMAT]),
    required=False,
    default=None,
    envvar=None,
    help="Specify the exact run date to inspect. Overrides the default interactive prompts for choosing the run date to inspect.",
)
@click.pass_context
def inspect_stats(ctx, config: str, run_date: datetime | None = None) -> None:
    app_settings = get_app_settings(src_yaml_filepath=Path(config), cli_overrides=ctx.obj.get(_GROUP_PARAMS_KEY))
    # if the user doesn't provide a --run-date value, prompt the user for the required run_date information.
    if not run_date:
        _LOGGER.info("Explicit --run-date not provided. Will run in interactive mode.")
        try:
            run_date = prompt_user_for_run_date(
                summaries_directory_path=app_settings.get_root_summary_directory_path(),
                date_str_format=RUN_DATE_STR_FORMAT,
            )
        except StatsRunPickerException:  # pragma: no cover
            _LOGGER.error("No run prior run summaries available for inspection.")
            ctx.exit(2)
    PriorRunStats(app_settings=app_settings, run_date=run_date).print_summary_tables()  # type: ignore


@cli.command(
    help="Output the contents of your existing config.yaml, along with any default values and/or CLI option overrides.",
    short_help="Output the current state of your app config for inspection.",
)
@config_path_option
@click.pass_context
def conf(ctx, config: str) -> None:
    app_settings = get_app_settings(src_yaml_filepath=Path(config), cli_overrides=ctx.obj.get(_GROUP_PARAMS_KEY))
    pprint(show_config_action(app_settings=app_settings))


@cli.command(
    help="Helper command to inspect or empty the local run cache(s). See this docs page for more info on the run cache: https://github.com/windexvalence/plastered/blob/main/docs/config_reference.md",
    short_help="Helper command to inspect or empty the local run cache(s).",
)
@config_path_option
@subcommand_flag("--info", help_msg="Print meta-info about the disk cache(s).")
@subcommand_flag("--empty", help_msg="When present, clear cache specified by the command argument.")
@subcommand_flag("--check", help_msg="Verify / try to fix diskcache consistency for specified cache argument.")
@subcommand_flag("--list-keys", help_msg="When present, list all the current keys available in the cache")
@click.option(
    "--read-value",
    type=click.STRING,
    required=False,
    default=None,
    envvar=None,
    help="Retrieves the string representation of the value for the specified cache key.",
)
@click.argument(
    "target_cache", envvar=None, type=click.Choice([CACHE_TYPE_API, CACHE_TYPE_SCRAPER, CLI_ALL_CACHE_TYPES])
)
@click.pass_context
def cache(
    ctx,
    config: str,
    target_cache: str,
    info: bool | None = False,
    empty: bool | None = False,
    check: bool | None = False,
    list_keys: bool | None = False,
    read_value: str | None = None,
) -> None:
    app_settings = get_app_settings(src_yaml_filepath=Path(config), cli_overrides=ctx.obj.get(_GROUP_PARAMS_KEY))
    cache_action(
        app_settings=app_settings,
        target_cache=target_cache,
        info=info,
        empty=empty,
        check=check,
        list_keys=list_keys,
        read_value=read_value,
    )


@cli.command(
    help="Output the contents of a template starter config to aid in initial app setup. Output may be redirected to the desired config filepath on your host machine.",
    short_help="Output the contents of a starter config template for initial setup.",
)
def init_conf() -> None:
    raw_init_conf_data_str = load_init_config_template()
    print(raw_init_conf_data_str)


if __name__ == "__main__":  # pragma: no cover
    cli(prog_name="plastered")
