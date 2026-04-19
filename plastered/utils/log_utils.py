# pragma: no cover
import os
from typing import Final

from rich.console import Console
from rich.logging import RichHandler

FORMAT = "%(message)s"
TERMINAL_COLS: Final[int] = int(os.getenv("COLUMNS", 120))
BAR_WIDTH: Final[int] = min(40, TERMINAL_COLS)
CONSOLE: Final[Console] = Console(width=TERMINAL_COLS)
DATE_FORMAT = "[%m/%d/%Y %H:%M:%S]"
LOG_TIME_FORMAT = "%m/%d/%Y %H:%M:%S"
SPINNER: Final[str] = "dots2"


def create_rich_log_handler() -> RichHandler:
    """Returns a rich.logging.RichHandler instance, intended to be passed into the root logger only."""
    # https://stackoverflow.com/a/68878216
    return RichHandler(
        # TODO: most likely need to also update this specific handler's level in the cli entrypoint as well.
        level="NOTSET",
        console=CONSOLE,
        log_time_format=LOG_TIME_FORMAT,
        omit_repeated_times=False,
        tracebacks_word_wrap=False,
    )
