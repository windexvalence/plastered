import csv
import os
from typing import Any, Callable, Dict, List
from unittest.mock import call, patch

import pytest
from rich.table import Column

from plastered.stats.stats import (
    FailedSnatchSummaryTable,
    RunCacheSummaryTable,
    SkippedReason,
    SkippedSummaryTable,
    SnatchFailureReason,
    SnatchSummaryTable,
    StatsTable,
    print_and_save_all_searcher_stats,
)
from plastered.utils.exceptions import StatsTableException


def _noop_col_fn(x: Any) -> Any:
    return x


@pytest.fixture(scope="session")
def skipped_rows() -> List[List[str]]:
    return [
        ["album", "similar-artist", "Some Artist", "Their Album", "N/A", "69420", SkippedReason.ALREADY_SNATCHED.value],
        [
            "album",
            "similar-artist",
            "Some Other Artist",
            "Other Album",
            "N/A",
            "69420",
            SkippedReason.ABOVE_MAX_SIZE.value,
        ],
        ["album", "similar-artist", "Another Artist", "Fake Album", "N/A", "None", SkippedReason.NO_MATCH_FOUND.value],
        [
            "album",
            "in-library",
            "Another Artist",
            "Fake Album",
            "N/A",
            "None",
            SkippedReason.REC_CONTEXT_FILTERING.value,
        ],
        [
            "track",
            "in-library",
            "Another Artist",
            "Fake Release",
            "Some Track",
            "None",
            SkippedReason.REC_CONTEXT_FILTERING.value,
        ],
    ]


@pytest.fixture(scope="session")
def failed_snatch_rows() -> List[List[str]]:
    return [
        ["redacted.sh/torrents.php?torrentid=69", "abcde1-gfhe39", SnatchFailureReason.RED_API_REQUEST_ERROR.value],
        ["redacted.sh/torrents.php?torrentid=420", "asjh98uf2f-fajsdknau", SnatchFailureReason.FILE_ERROR.value],
        ["redacted.sh/torrents.php?torrentid=666", "ajdff2favdfvkj", SnatchFailureReason.OTHER.value],
    ]


@pytest.fixture(scope="session")
def snatch_summary_rows() -> List[List[str]]:
    return [
        [
            "album",
            "similar-artist",
            "Some Artist",
            "Their Album",
            "N/A",
            "69420",
            "Vinyl",
            "no",
            "/downloads/69420.torrent",
        ],
        ["album", "similar-artist", "Fake Band", "Fake Album", "N/A", "69", "CD", "yes", "/downloads/69.torrent"],
        [
            "track",
            "similar-artist",
            "Fake Band",
            "Fake Album",
            "Fake Song",
            "420",
            "CD",
            "yes",
            "/downloads/420.torrent",
        ],
    ]


@pytest.mark.parametrize(
    "bad_fn_mapping",
    [
        ({-1: _noop_col_fn}),
        ({0: _noop_col_fn, 1: _noop_col_fn, 2: _noop_col_fn, 3: _noop_col_fn}),
    ],
)
def test_invalid_stats_table_construction(tmp_path: pytest.FixtureRequest, bad_fn_mapping: Dict[int, Callable]) -> None:
    with pytest.raises(StatsTableException, match="Invalid cell_idxs_to_style_fns value"):
        bad_st = StatsTable(
            title="Should fail",
            columns=[Column(header="First Col"), Column(header="Second Col")],
            tsv_output_path=os.path.join(tmp_path, "bad_st.tsv"),
            cell_idxs_to_style_fns=bad_fn_mapping,
        )


def test_invalid_add_rows(tmp_path: pytest.FixtureRequest) -> None:
    test_st = StatsTable(
        title="Should fail",
        columns=[Column(header="First Col"), Column(header="Second Col")],
        tsv_output_path=os.path.join(tmp_path, "bad_st.tsv"),
    )
    rows_to_add = [["a", "b"], ["c", "d", "e"]]
    with pytest.raises(StatsTableException, match="Invalid row provided: length"):
        test_st.add_rows(rows=rows_to_add)


@pytest.mark.parametrize(
    "hit_rate_str, expected",
    [
        ("NA", "white"),
        ("0.0", "red3"),
        ("0.125", "red3"),
        ("0.249", "red3"),
        ("0.25", "dark_orange3"),
        ("0.499", "dark_orange3"),
        ("0.5", "green_yellow"),
        ("0.749", "green_yellow"),
        ("0.75", "green"),
        ("1.00", "green"),
    ],
)
def test_run_cache_summary_table_stylize_cache_hit_rate_entry(
    hit_rate_str: str,
    expected: str,
) -> None:
    actual = RunCacheSummaryTable.stylize_cache_hit_rate_entry(hit_rate_str=hit_rate_str)
    assert actual == expected, f"Expected '{expected}', but got '{actual}'"


def test_run_cache_summary_table_constructor(tmp_path: pytest.FixtureRequest) -> None:
    with patch.object(RunCacheSummaryTable, "add_row") as mock_st_add_row:
        mock_st_add_row.return_value = None
        rcst = RunCacheSummaryTable(
            cache_type_str="api",
            disk_usage_mb="100.0",
            hits="69",
            misses="420",
            hit_rate="0.1411",
            directory_path=str(tmp_path),
        )
        for k, v in rcst._per_row_cell_style_fns.items():
            if k != 3:
                assert v is None
            else:
                assert v is not None and callable(v)
        mock_st_add_row.assert_called_once_with(["100.0", "69", "420", "0.1411", str(tmp_path)])


@pytest.mark.parametrize(
    "expected_tsv_suffix, expected_tsv_row_cnt",
    [
        ("_skipped.tsv", 6),
        ("_failed.tsv", 4),
        ("_snatched.tsv", 4),
    ],
)
def test_print_and_save_all_searcher_stats(
    tmp_path: pytest.FixtureRequest,
    skipped_rows: List[List[str]],
    failed_snatch_rows: List[List[str]],
    snatch_summary_rows: List[List[str]],
    expected_tsv_suffix: str,
    expected_tsv_row_cnt: int,
) -> None:
    output_filepath_prefix = os.path.join(tmp_path, "2025-01-11_21-33-32")
    expected_tsv_filepath = os.path.join(tmp_path, f"{output_filepath_prefix}{expected_tsv_suffix}")
    print_and_save_all_searcher_stats(
        skipped_rows=skipped_rows,
        failed_snatch_rows=failed_snatch_rows,
        snatch_summary_rows=snatch_summary_rows,
        output_filepath_prefix=output_filepath_prefix,
    )
    assert os.path.exists(expected_tsv_filepath), f"Expected {expected_tsv_filepath} path to exist, but foes not."
    actual_row_cnt = 0
    with open(expected_tsv_filepath, "r") as f:
        tsv_reader = csv.reader(f, delimiter="t")
        actual_row_cnt = len([row for row in tsv_reader])
    assert (
        actual_row_cnt == expected_tsv_row_cnt
    ), f"Expected output tsv to have {expected_tsv_row_cnt} rows, but got {actual_row_cnt}"
