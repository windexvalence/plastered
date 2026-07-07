"""Slim CLI entrypoint for the plastered server. Usage: `plastered run --config <path-to-config.yaml>`."""

import logging
import os
from pathlib import Path

import click

from plastered.config.app_settings import get_app_settings
from plastered.config.cli_state import CliState
from plastered.utils.constants import PLASTERED_CONFIG_ENVVAR
from plastered.utils.log_utils import create_stream_log_handler
from plastered.version import get_project_version


@click.version_option(version=get_project_version(), prog_name="plastered")
@click.group(help="plastered: finds your Last.fm recs and snatches them from RED, via a web UI.")
def cli() -> None:
    """Top-level CLI group."""


@cli.command()
@click.option(
    "-c",
    "--config",
    required=True,
    envvar=PLASTERED_CONFIG_ENVVAR,
    show_envvar=True,
    help="The path to your plastered configuration file.",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, resolve_path=True, path_type=Path),
)
def run(config: Path) -> None:
    """Run the plastered web server with the provided configuration."""
    # Function-scoped import for quick CLI load times.
    import uvicorn

    cli_state = CliState(resolved_config_path=config, app_settings=get_app_settings(src_yaml_filepath=config))
    # Required for uvicorn logging to be at all configurable: https://github.com/Kludex/uvicorn/issues/945#issuecomment-819692145
    logging.basicConfig(level=cli_state.app_settings.server.log_level, handlers=[create_stream_log_handler()])
    # uvicorn imports the app factory itself (in a fresh process when workers > 1), and the factory's lifespan resolves
    # the config path from the environment — so propagate the CLI-provided path there.
    os.environ[PLASTERED_CONFIG_ENVVAR] = os.fspath(cli_state.resolved_config_path)
    server_config = cli_state.app_settings.server
    uvicorn.run(
        "plastered.api.app:create_fastapi_app",
        factory=True,
        host=server_config.host,
        port=server_config.port,
        log_level=server_config.log_level.lower(),
        # Keep the worker count config-driven: RED's per-process rate limit stays globally correct only when this is 1
        # (see ServerConfig). Note uvicorn ignores `workers` when `reload=True`, so this launch path does not reload.
        workers=server_config.workers,
    )


if __name__ == "__main__":
    cli(prog_name="plastered")
