# pragma: no cover
import logging
import os
import sys
from typing import Final

from rich.console import Console
from rich.logging import RichHandler

FORMAT = "%(message)s"
STREAM_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
TERMINAL_COLS: Final[int] = int(os.getenv("COLUMNS", 120))
BAR_WIDTH: Final[int] = min(40, TERMINAL_COLS)
CONSOLE: Final[Console] = Console(width=TERMINAL_COLS)
DATE_FORMAT = "[%m/%d/%Y %H:%M:%S]"
LOG_TIME_FORMAT = "%m/%d/%Y %H:%M:%S"
SPINNER: Final[str] = "dots2"


def create_stream_log_handler() -> logging.Handler:
    """
    Returns a plain stdlib `logging.StreamHandler` (writing to stderr) for use when the application is not running
    under `rich` -- e.g. when launched as the FastAPI server -- so logs are emitted via the builtin logging module
    rather than `rich.logging.RichHandler`.

    Intended as the log handler for the plastered server. See the `create_rich_log_handler` for CLI-based logging
    """
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(fmt=STREAM_FORMAT, datefmt=LOG_TIME_FORMAT))
    return handler


def create_rich_log_handler() -> RichHandler:
    """
    Returns a rich.logging.RichHandler instance, intended to be passed into the root logger. This function should only
    be called from cli.py when plastered is run as a CLI, and not from the server application pathway.
    See `create_stream_log_handler` for API logging handler setup.
    """
    # https://stackoverflow.com/a/68878216
    return RichHandler(
        # NOTE: This handler's level is set by the cli entrypoint.
        level="NOTSET",
        console=CONSOLE,
        log_time_format=LOG_TIME_FORMAT,
        omit_repeated_times=False,
        tracebacks_word_wrap=False,
    )
