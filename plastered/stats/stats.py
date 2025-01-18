import csv
import logging
import re
from enum import StrEnum
from typing import Callable, Dict, List, Optional

from rich.console import Console
from rich.table import Column, Table
from rich.text import Text

from plastered.utils.constants import STATS_TRACK_REC_NONE
from plastered.utils.exceptions import RedClientSnatchException, StatsTableException

_LOGGER = logging.getLogger(__name__)


def _stylize_track_rec_entry(track_rec: str) -> str:
    return "white" if track_rec == STATS_TRACK_REC_NONE else "dark_magenta"


class SkippedReason(StrEnum):
    """Utility Enum for standardizing the summary output tables snatch skip reasons."""

    ABOVE_MAX_SIZE = "All RED matches' size > 'max_size_gb' config setting."
    NO_MATCH_FOUND = "No RED match found."
    ALREADY_SNATCHED = "Pre-existing user snatch found in release group."
    REC_CONTEXT_FILTERING = "LFM Recs with context 'in-library' ignored when 'allow_library_items' = false"


class SnatchFailureReason(StrEnum):
    """Utility Enum for standardizing the summary output tables error references."""

    RED_API_REQUEST_ERROR = RedClientSnatchException.__name__
    FILE_ERROR = OSError.__name__
    OTHER = "Exception - other"


class StatsTable:
    """
    Helper class to create a Rich table for summary outputs on the CLI.
    Additionally supports functions on a per-cell basis to conditionally
    stylize a columns' cell data base on its value.
    """

    def __init__(
        self,
        title: str,
        columns: List[Column],
        tsv_output_path: Optional[str] = None,
        cell_idxs_to_style_fns: Optional[Dict[int, Callable]] = {},
        caption: Optional[str] = None,
    ):
        self._title = title
        self._columns = columns
        self._tsv_output_path = tsv_output_path
        self._num_cols = len(self._columns)
        self._per_row_cell_style_fns = {}
        if len(cell_idxs_to_style_fns) > self._num_cols or any(
            [idx < 0 or self._num_cols <= idx for idx in cell_idxs_to_style_fns.keys()]
        ):
            raise StatsTableException(
                f"Invalid cell_idxs_to_style_fns value. Must not contain more entries than table has columns."
            )
        self._per_row_cell_style_fns = {
            i: cell_idxs_to_style_fns[i] if i in cell_idxs_to_style_fns else None for i in range(self._num_cols)
        }
        self._caption = caption
        self._table = Table(
            *columns,
            title=self._title,
            caption=self._caption,
            title_style="bold white",
            show_lines=True,
            expand=True,
        )
        self._raw_rows: List[List[str]] = []

    def add_row(self, row: List[str]) -> None:
        stylized_row = [
            (
                cell_data
                if not self._per_row_cell_style_fns[i]
                else Text(cell_data, style=self._per_row_cell_style_fns[i](cell_data))
            )
            for i, cell_data in enumerate(row)
        ]
        self._table.add_row(*stylized_row)
        self._raw_rows.append(row)

    def add_rows(self, rows: List[List[str]]) -> None:
        for row in rows:
            if len(row) != self._num_cols:
                raise StatsTableException(
                    f"Invalid row provided: length {len(row)}, but StatsTable instance has {self._num_cols} columns {row}"
                )
            self.add_row(row)

    def print_table(self) -> None:
        console = Console()
        console.print(self._table)

    def to_tsv_file(self) -> None:
        tsv_header = [re.sub(r"\s+", "_", col.header) for col in self._table.columns]
        try:
            with open(self._tsv_output_path, "w") as f:
                tsv_writer = csv.writer(f, delimiter="\t", lineterminator="\n")
                tsv_writer.writerow(tsv_header)
                tsv_writer.writerows(self._raw_rows)
        except Exception:  # pragma: no cover
            _LOGGER.error(
                f"Failed to write TSV file for {self.__class__.__name__} to filepath: {self._tsv_output_path}",
                exc_info=True,
            )

    def print_and_save(self) -> None:
        self.print_table()
        self.to_tsv_file()


class SkippedSummaryTable(StatsTable):
    """Utility subclass of StatsTable for printing skipped snatch stats."""

    @staticmethod
    def stylize_skip_reason_entry(reason: str) -> str:
        entry_enum = SkippedReason(reason)
        if entry_enum == SkippedReason.ABOVE_MAX_SIZE:
            return "dark_orange3"
        if entry_enum == SkippedReason.ALREADY_SNATCHED:
            return "green"
        if entry_enum == SkippedReason.NO_MATCH_FOUND:
            return "red3"
        return "white"

    def __init__(self, rows: List[List[str]], tsv_output_path: str):
        super().__init__(
            title="Unsnatched / Skipped LFM Recs",
            columns=[
                Column(header="Type", justify="left", no_wrap=True),
                Column(header="LFM Rec context", no_wrap=True),
                Column(header="Artist", style="cyan", no_wrap=False),
                Column(header="Release", style="magenta", no_wrap=False),
                Column(header="Track Rec", no_wrap=False),
                Column(header="Skip reason", no_wrap=False),
            ],
            tsv_output_path=tsv_output_path,
            cell_idxs_to_style_fns={4: _stylize_track_rec_entry, 5: self.stylize_skip_reason_entry},
            caption="Summary of LFM Recs which were either not found on RED, or ignored based on the search config settings.",
        )
        self.add_rows(rows)


class FailedSnatchSummaryTable(StatsTable):
    """Utility subclass of StatsTable for printing snatch failure stats."""

    @staticmethod
    def stylize_failure_reason_entry(failure_reason: str) -> str:
        failure_enum = SnatchFailureReason(failure_reason)
        if failure_enum == SnatchFailureReason.RED_API_REQUEST_ERROR:
            return "red3"
        if failure_enum == SnatchFailureReason.FILE_ERROR:
            return "dark_orange3"
        return "bright_red"

    def __init__(self, rows: List[List[str]], tsv_output_path: str):
        super().__init__(
            title="Failed Downloads",
            columns=[
                Column(header="RED permalink", justify="left", no_wrap=True, ratio=1),
                Column(header="Matched MBID (if any)", no_wrap=True, ratio=1),
                Column(header="Failure reason", style="bright_red", no_wrap=True, ratio=1),
            ],
            tsv_output_path=tsv_output_path,
            cell_idxs_to_style_fns={2: self.stylize_failure_reason_entry},
        )
        self.add_rows(rows)


class SnatchSummaryTable(StatsTable):
    """Utility subclass of StatsTable for printing successful snatch stats."""

    def __init__(self, rows: List[List[str]], tsv_output_path: str):
        super().__init__(
            title="Snatched LFM Recs",
            columns=[
                Column(header="Type", justify="left", no_wrap=True, ratio=1),
                Column(header="LFM Rec context", no_wrap=False, ratio=1),
                Column(header="Artist", style="cyan", no_wrap=False, ratio=1),
                Column(header="Release", style="magenta", no_wrap=False, ratio=1),
                Column(header="Track Rec", no_wrap=False),
                Column(header="RED tid", no_wrap=True, ratio=1),
                Column(header="Media", no_wrap=True, ratio=1),
                Column(header="FL token used", style="green", no_wrap=True, ratio=1),
                Column(header="Snatch path", no_wrap=True, ratio=1),
            ],
            tsv_output_path=tsv_output_path,
            cell_idxs_to_style_fns={4: _stylize_track_rec_entry, 7: lambda fl: "green" if fl == "yes" else "white"},
            caption="Summary of LFM Recs successfully found on RED and snatched.",
        )
        self.add_rows(rows)


class RunCacheSummaryTable(StatsTable):
    """Utility subclass of StatsTable for printing RunCache stats."""

    @staticmethod
    def stylize_cache_hit_rate_entry(hit_rate_str: str) -> str:
        if hit_rate_str == "NA":
            return "white"
        hit_rate = float(hit_rate_str)
        if 0 <= hit_rate < 0.25:
            return "red3"
        if 0.25 <= hit_rate < 0.5:
            return "dark_orange3"
        if 0.5 <= hit_rate < 0.75:
            return "green_yellow"
        return "green"

    def __init__(
        self, cache_type_str: str, disk_usage_mb: str, hits: str, misses: str, hit_rate: str, directory_path: str
    ):
        super().__init__(
            title=f"Cache Summary: {cache_type_str}",
            columns=[
                Column(header="Disk Usage (MB)", justify="left", no_wrap=False, ratio=1),
                Column(header="Cache hits (prior run)", no_wrap=False, ratio=1),
                Column(header="Cache misses (prior run)", no_wrap=False, ratio=1),
                Column(header="Cache hit rate (prior run)", no_wrap=False, ratio=1),
                Column(header="Directory path in container", no_wrap=False, ratio=2),
            ],
            cell_idxs_to_style_fns={3: self.stylize_cache_hit_rate_entry},
        )
        self.add_row([disk_usage_mb, hits, misses, hit_rate, directory_path])


def print_and_save_all_searcher_stats(
    skipped_rows: List[List[str]],
    failed_snatch_rows: List[List[str]],
    snatch_summary_rows: List[List[str]],
    output_filepath_prefix: str,
) -> None:
    SkippedSummaryTable(rows=skipped_rows, tsv_output_path=f"{output_filepath_prefix}_skipped.tsv").print_and_save()
    FailedSnatchSummaryTable(
        rows=failed_snatch_rows, tsv_output_path=f"{output_filepath_prefix}_failed.tsv"
    ).print_and_save()
    SnatchSummaryTable(
        rows=snatch_summary_rows, tsv_output_path=f"{output_filepath_prefix}_snatched.tsv"
    ).print_and_save()
