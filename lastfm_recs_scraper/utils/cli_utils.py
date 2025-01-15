"""
Contains a few helper decorators / functions to reduce the repeated code in cli.py.
"""

from functools import wraps

import click


DEFAULT_VERBOSITY = "WARNING"


# Adopted from here to reduce repeat code: https://github.com/pallets/click/issues/108#issuecomment-280489786
def config_path_option(func):
    @click.option(
        "-c", "--config",
        required=True,
        envvar="PLASTERED_CONFIG",
        show_envvar=True,
        type=click.Path(exists=True),
        help="Absolute path to the application config.yaml file.",
    )
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


def subcommand_flag(name, help):
    def decorator(func):
        @click.option(name, envvar=None, is_flag=True, default=False, help=help)
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator
