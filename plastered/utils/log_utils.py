# pragma: no cover
import os
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from enum import StrEnum, unique

from rich.console import Console, RenderableType
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

FORMAT = "%(message)s"
TERMINAL_COLS = int(os.getenv("COLUMNS", 120))
BAR_WIDTH = min(40, TERMINAL_COLS)
CONSOLE = Console(width=TERMINAL_COLS)
DATE_FORMAT = "[%m/%d/%Y %H:%M:%S]"
LOG_TIME_FORMAT = "%m/%d/%Y %H:%M:%S"
SPINNER = "dots2"


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


def prog_args() -> tuple[ProgressColumn, ...]:
    """Helper function for returning a standard set of args to pass into a `rich.Progress` context manager."""
    return (
        SpinnerColumn(spinner_name=SPINNER),
        TextColumn("[progress.description]{task.description}"),
        MofNCompleteColumn(),
        BarColumn(bar_width=BAR_WIDTH),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    )


def prog_kwargs() -> dict[str, bool | Console]:
    """Helper function for returning a standard set of kwargs to pass into a `rich.Progress` context manager."""
    return {"transient": True, "console": CONSOLE}


@unique
class ProgType(StrEnum):
    """
    Utility `StrEnum` class for distinguishing the different types of `rich.Progress` task types.
    Used by the custom subclass of `Progress` defined below for per-progress-bar-type column rendering.
    """

    RED_BROWSE = "red-browse"
    RED_SNATCH = "red-snatch"
    STANDARD = "standard"


class NestedProgress(Progress):
    """
    Custom subclass of `rich.progress.Progress` which allows for distinct sub_task progress bar styles.
    Adopted from the solution decribed in the link below:
    https://github.com/Textualize/rich/discussions/950#discussioncomment-300794
    """

    type_strs_to_prog_bar_types: dict[str, ProgType] = {member.value: member for member in ProgType}

    def __init__(self):
        super().__init__(*prog_args(), **prog_kwargs())

    def add_red_browse_task(self, release_name: str, artist_name: str) -> TaskID:
        """
        Util method for automatically setting the new child progress bar task settings for the red-browse progress bar.
        """
        task_id = self.add_task(
            description=f"[yellow] Searching '{release_name}' by '{artist_name}' on RED API",
            total=None,
            progress_type=ProgType.RED_BROWSE,
        )
        return task_id

    def get_renderables(self) -> Iterable[RenderableType]:
        for task in self.tasks:
            if (
                task.fields.get("progress_type") == ProgType.RED_BROWSE
                or task.fields.get("progress_type") == ProgType.RED_SNATCH
            ):
                self.columns = (
                    SpinnerColumn(),  # spinner_name=SPINNER),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(BAR_WIDTH),
                    TimeElapsedColumn(),
                )
            else:
                self.columns = prog_args()
            yield self.make_tasks_table([task])


@contextmanager
def red_browse_progress(
    release_name: str, artist_name: str, parent_prog: NestedProgress | None
) -> Iterator[RenderableType | None]:
    try:
        child_task_id = None
        if parent_prog is not None:
            child_task_id = parent_prog.add_red_browse_task(release_name=release_name, artist_name=artist_name)
        yield child_task_id
    finally:
        if not parent_prog or not child_task_id:
            pass
        else:
            parent_prog.remove_task(child_task_id)
