import csv
from datetime import datetime
import os
from pathlib import Path
from typing import Any, Callable, Dict, List
from unittest.mock import call, patch

import pytest
from rich.table import Column

from plastered.config.config_parser import AppConfig
from plastered.stats.stats import (
    FailedSnatchSummaryTable,
    RunCacheSummaryTable,
    SkippedReason,
    SkippedSummaryTable,
    SnatchFailureReason,
    SnatchSummaryTable,
    StatsTable,
    PriorRunStats,
    print_and_save_all_searcher_stats,
    _FAILED,
    _FAILED_FILENAME,
    _get_rows_from_tsv,
    _SKIPPED,
    _SKIPPED_FILENAME,
    _SNATCHED,
    _SNATCHED_FILENAME,
)
from plastered.utils.constants import RUN_DATE_STR_FORMAT
from plastered.utils.exceptions import PriorRunStatsException, StatsTableException
from tests.conftest import valid_app_config, mock_run_date_str


def _noop_col_fn(x: Any) -> Any:
    return x


@pytest.fixture(scope="session")
def mock_root_summary_dir_path(tmp_path_factory: pytest.FixtureRequest) -> Path:
    return tmp_path_factory.mktemp("summaries")


@pytest.fixture(scope="session")
def mock_output_summary_dir_path(mock_root_summary_dir_path: Path, mock_run_date_str: str) -> Path:
    run_summary_dir = mock_root_summary_dir_path / mock_run_date_str
    run_summary_dir.mkdir()
    return run_summary_dir


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


@pytest.fixture(scope="session")
def mock_summary_tsvs(
    mock_output_summary_dir_path: Path,
    failed_snatch_rows: List[List[str]],
    skipped_rows: List[List[str]],
    snatch_summary_rows: List[List[str]],
) -> Dict[str, str]:
    type_to_headers = {
        _FAILED: ["RED_permalink", "Matched_MBID_(if_any)", "Failure_reason"],
        _SNATCHED: [
            "Type", "LFM_Rec_context", "Artist", "Release", "Track_Rec", "RED_tid", "Media", "FL_token_used", "Snatch_path",
        ],
        _SKIPPED: [
            "Type", "LFM_Rec_context", "Artist", "Release", "Track_Rec", "Matched_RED_TID", "Skip_reason",
        ],
    }
    def _write_dummy_tsv(dummy_path: str, header: List[str], dummy_rows: List[List[str]]) -> None:
        with open(dummy_path, "w") as f:
            w = csv.writer(f, delimiter="\t", lineterminator="\n")
            w.writerow(header)
            w.writerows(dummy_rows)
    failed_tsv_path = os.path.join(mock_output_summary_dir_path, _FAILED_FILENAME)
    snatched_tsv_path = os.path.join(mock_output_summary_dir_path, _SNATCHED_FILENAME)
    skipped_tsv_path = os.path.join(mock_output_summary_dir_path, _SKIPPED_FILENAME)
    _write_dummy_tsv(failed_tsv_path, type_to_headers[_FAILED], failed_snatch_rows)
    _write_dummy_tsv(snatched_tsv_path, type_to_headers[_SNATCHED], snatch_summary_rows)
    _write_dummy_tsv(skipped_tsv_path, type_to_headers[_SKIPPED], skipped_rows)
    return {
        _FAILED: failed_tsv_path,
        _SNATCHED: snatched_tsv_path,
        _SKIPPED: skipped_tsv_path,
    }


@pytest.mark.parametrize(
    "table_type, expected_rows_fixture_name", [
        ("failed", "failed_snatch_rows"),
        ("skipped", "snatch_summary_rows"),
        ("snatched", "skipped_rows"),
    ]
)
def test_get_rows_from_tsv(
    request: pytest.FixtureRequest,
    mock_summary_tsvs: Dict[str, str],
    table_type: str,
    expected_rows_fixture_name: str,
) -> None:
    tsv_filepath = mock_summary_tsvs[table_type]
    expected_rows = request.getfixturevalue(expected_rows_fixture_name)
    expected_rows_set = set([tuple(row) for row in expected_rows])
    actual = _get_rows_from_tsv(tsv_path=tsv_filepath)
    actual_rows_set = set([tuple(row) for row in expected_rows_set])
    print(f"actual[0]: {actual[0]}")
    print(f"expected_rows[0]: {expected_rows[0]}")
    assert actual_rows_set == expected_rows_set


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
            tsv_path=os.path.join(tmp_path, "bad_st.tsv"),
            cell_idxs_to_style_fns=bad_fn_mapping,
        )


def test_invalid_to_tsv_file(tmp_path: pytest.FixtureRequest) -> None:
    test_st = StatsTable(
        title="should fail",
        columns=[Column(header="foo")],
        tsv_path=os.path.join(tmp_path, "bad_st.tsv"),
        read_only=True,
    )
    with pytest.raises(StatsTableException, match="Unexpected to_tsv_file call on a StatsTable instance with read_only"):
        test_st.to_tsv_file()


def test_invalid_add_rows(tmp_path: pytest.FixtureRequest) -> None:
    test_st = StatsTable(
        title="Should fail",
        columns=[Column(header="First Col"), Column(header="Second Col")],
        tsv_path=os.path.join(tmp_path, "bad_st.tsv"),
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
    "expected_tsv_filename, expected_tsv_row_cnt",
    [
        ("skipped.tsv", 6),
        ("failed.tsv", 4),
        ("snatched.tsv", 4),
    ],
)
def test_print_and_save_all_searcher_stats(
    tmp_path: pytest.FixtureRequest,
    skipped_rows: List[List[str]],
    failed_snatch_rows: List[List[str]],
    snatch_summary_rows: List[List[str]],
    expected_tsv_filename: str,
    expected_tsv_row_cnt: int,
) -> None:
    output_summary_dir_path = os.path.join(tmp_path, "2025-01-11_21-33-32")
    expected_tsv_filepath = os.path.join(output_summary_dir_path, expected_tsv_filename)
    print_and_save_all_searcher_stats(
        skipped_rows=skipped_rows,
        failed_snatch_rows=failed_snatch_rows,
        snatch_summary_rows=snatch_summary_rows,
        output_summary_dir_path=output_summary_dir_path,
    )
    assert os.path.exists(expected_tsv_filepath), f"Expected {expected_tsv_filepath} path to exist, but foes not."
    actual_row_cnt = 0
    with open(expected_tsv_filepath, "r") as f:
        tsv_reader = csv.reader(f, delimiter="t")
        actual_row_cnt = len([row for row in tsv_reader])
    assert (
        actual_row_cnt == expected_tsv_row_cnt
    ), f"Expected output tsv to have {expected_tsv_row_cnt} rows, but got {actual_row_cnt}"


def test_init_prior_run_stats(
    valid_app_config: AppConfig,
    mock_output_summary_dir_path: Path,
    mock_summary_tsvs: Dict[str, str],
    mock_run_date_str: str,
) -> None:
    with patch.object(AppConfig, "get_output_summary_dir_path") as mock_get_output_summary_dir_path:
        mock_get_output_summary_dir_path.return_value = str(mock_output_summary_dir_path)
        with patch("plastered.stats.stats._get_tsv_output_filepaths") as mock_get_tsv_output_filepaths:
            mock_get_tsv_output_filepaths.return_value = mock_summary_tsvs
            prs = PriorRunStats(
                app_config=valid_app_config, run_date=datetime.strptime(mock_run_date_str, RUN_DATE_STR_FORMAT),
            )
            prs.print_summary_tables()


def test_bad_init_prior_run_stats(
    valid_app_config: AppConfig,
    mock_output_summary_dir_path: Path,
    mock_summary_tsvs: Dict[str, str],
) -> None:
    with patch.object(AppConfig, "get_output_summary_dir_path") as mock_get_output_summary_dir_path:
        mock_get_output_summary_dir_path.return_value = str(mock_output_summary_dir_path)
        with patch("plastered.stats.stats._get_tsv_output_filepaths") as mock_get_tsv_output_filepaths:
            mock_get_tsv_output_filepaths.return_value = {
                _FAILED: os.path.join("not", "a", "real", "path"),
                _SKIPPED: os.path.join("not", "a", "real", "path"),
                _SNATCHED: os.path.join("not", "a", "real", "path"),
            }
            with pytest.raises(PriorRunStatsException, match="One or more summary tsvs for run date"):
                prs = PriorRunStats(
                    app_config=valid_app_config, run_date=datetime.now(),
                )
