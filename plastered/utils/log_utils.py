# pragma: no cover
import logging
import os
import sys
from typing import Final

from rich.console import Console

STREAM_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
TERMINAL_COLS: Final[int] = int(os.getenv("COLUMNS", 120))
CONSOLE: Final[Console] = Console(width=TERMINAL_COLS)
LOG_TIME_FORMAT = "%m/%d/%Y %H:%M:%S"
SPINNER: Final[str] = "dots2"


def create_stream_log_handler() -> logging.Handler:
    """
    Returns a plain stdlib `logging.StreamHandler` (writing to stderr) used as the log handler for the plastered
    (FastAPI) server, so logs are emitted via the builtin logging module. `rich` is still used for the console
    spinner (`CONSOLE`/`SPINNER`) during scrape/search runs.
    """
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(fmt=STREAM_FORMAT, datefmt=LOG_TIME_FORMAT))
    return handler
