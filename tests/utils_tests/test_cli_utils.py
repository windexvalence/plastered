import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest

from plastered.utils.cli_utils import StatsRunPicker
from plastered.utils.constants import RUN_DATE_STR_FORMAT
from tests.conftest import (
    mock_output_summary_dir_path,
    mock_root_summary_dir_path,
    mock_summary_tsvs,
    valid_app_config,
)


def test_init_stats_run_picker(
    mock_root_summary_dir_path: Path,
    mock_output_summary_dir_path: Path,
    mock_summary_tsvs: Dict[str, str],
) -> None:
    srp = StatsRunPicker(
        summaries_directory_path=mock_root_summary_dir_path,
        date_str_format=RUN_DATE_STR_FORMAT,
    )
    assert len(srp._possible_datetimes) > 0
    assert srp._candidate_dt.year == 1970
    assert srp._candidate_dt.month == 1
    assert srp._candidate_dt.day == 1


@pytest.mark.parametrize(
    "dt_attr_name, dt_arg, candidate_dt, expected",
    [
        ("month", datetime(year=1969, month=2, day=15), datetime(year=1970, month=1, day=1), False),
        ("month", datetime(year=1970, month=2, day=15), datetime(year=1970, month=1, day=1), True),
        ("day", datetime(year=1970, month=2, day=15), datetime(year=1970, month=1, day=1), False),
        ("day", datetime(year=1970, month=2, day=15), datetime(year=1970, month=2, day=1), True),
        ("hour", datetime(year=1970, month=2, day=15), datetime(year=1970, month=2, day=1), False),
        ("hour", datetime(year=1970, month=2, day=15), datetime(year=1970, month=2, day=15), True),
        ("minute", datetime(year=1970, month=2, day=15, hour=1), datetime(year=1970, month=2, day=15, hour=0), False),
        ("minute", datetime(year=1970, month=2, day=15, hour=2), datetime(year=1970, month=2, day=15, hour=2), True),
        (
            "second",
            datetime(year=1970, month=2, day=15, hour=2, minute=30),
            datetime(year=1970, month=2, day=15, hour=2, minute=0),
            False,
        ),
        (
            "second",
            datetime(year=1970, month=2, day=15, hour=2, minute=31),
            datetime(year=1970, month=2, day=15, hour=2, minute=31),
            True,
        ),
    ],
)
def test_stats_run_picker_is_valid_candidate_dt(
    mock_root_summary_dir_path: Path,
    mock_output_summary_dir_path: Path,
    mock_summary_tsvs: Dict[str, str],
    dt_attr_name: str,
    dt_arg: datetime,
    candidate_dt: datetime,
    expected: bool,
) -> None:
    srp = StatsRunPicker(
        summaries_directory_path=mock_root_summary_dir_path,
        date_str_format=RUN_DATE_STR_FORMAT,
    )
    srp._candidate_dt = candidate_dt
    actual = srp._is_valid_candidate_dt(dt=dt_arg, dt_attr_name=dt_attr_name)
    assert actual == expected


@pytest.mark.parametrize(
    "dt_attr_name, mock_possible_datetimes, expected",
    [
        (
            "year",
            [
                datetime(year=2025, month=1, day=15, hour=2, minute=31, second=25),
                datetime(year=2024, month=12, day=15, hour=2, minute=31, second=25),
            ],
            ["2024", "2025"],
        ),
        (
            "month",
            [
                datetime(year=2025, month=2, day=15, hour=2, minute=31, second=25),
                datetime(year=2025, month=1, day=15, hour=2, minute=31, second=25),
            ],
            ["1", "2"],
        ),
        (
            "day",
            [
                datetime(year=2025, month=2, day=15, hour=2, minute=31, second=25),
                datetime(year=2025, month=2, day=1, hour=2, minute=31, second=25),
                datetime(year=2025, month=2, day=22, hour=2, minute=31, second=25),
                datetime(year=2025, month=2, day=10, hour=2, minute=31, second=25),
            ],
            ["1", "10", "15", "22"],
        ),
        (
            "hour",
            [
                datetime(year=2025, month=2, day=15, hour=1, minute=31, second=25),
                datetime(year=2025, month=2, day=15, hour=23, minute=31, second=25),
                datetime(year=2025, month=2, day=15, hour=6, minute=31, second=25),
                datetime(year=2025, month=2, day=15, hour=2, minute=31, second=25),
            ],
            ["1", "2", "6", "23"],
        ),
        (
            "minute",
            [
                datetime(year=2025, month=2, day=15, hour=1, minute=31, second=25),
                datetime(year=2025, month=2, day=15, hour=1, minute=1, second=25),
                datetime(year=2025, month=2, day=15, hour=1, minute=3, second=25),
                datetime(year=2025, month=2, day=15, hour=1, minute=11, second=25),
            ],
            ["1", "3", "11", "31"],
        ),
        (
            "second",
            [
                datetime(year=2025, month=2, day=15, hour=1, minute=1, second=2),
                datetime(year=2025, month=2, day=15, hour=1, minute=1, second=25),
                datetime(year=2025, month=2, day=15, hour=1, minute=1, second=59),
                datetime(year=2025, month=2, day=15, hour=1, minute=1, second=45),
            ],
            ["2", "25", "45", "59"],
        ),
    ],
)
def test_stats_run_picker_get_dt_choices(
    mock_root_summary_dir_path: Path,
    mock_output_summary_dir_path: Path,
    mock_summary_tsvs: Dict[str, str],
    dt_attr_name: str,
    mock_possible_datetimes: List[datetime],
    expected: List[str],
) -> None:
    with patch.object(StatsRunPicker, "_is_valid_candidate_dt") as mock_is_valid_candidate_dt:
        mock_is_valid_candidate_dt.return_value = True
        srp = StatsRunPicker(
            summaries_directory_path=mock_root_summary_dir_path,
            date_str_format=RUN_DATE_STR_FORMAT,
        )
        srp._possible_datetimes = mock_possible_datetimes
        actual = srp._get_dt_choices(dt_attr_name=dt_attr_name)
        assert actual == expected


@pytest.mark.parametrize(
    "dt_attr_name, mock_user_input, expected_candidate_dt",
    [
        ("year", "2025", datetime(year=2025, month=1, day=1, hour=0, minute=0, second=0)),
        ("month", "2", datetime(year=1970, month=2, day=1, hour=0, minute=0, second=0)),
        ("day", "20", datetime(year=1970, month=1, day=20, hour=0, minute=0, second=0)),
        ("hour", "19", datetime(year=1970, month=1, day=1, hour=19, minute=0, second=0)),
        ("minute", "59", datetime(year=1970, month=1, day=1, hour=0, minute=59, second=0)),
        ("second", "30", datetime(year=1970, month=1, day=1, hour=0, minute=0, second=30)),
    ],
)
def test_prompt_date_component(
    mock_root_summary_dir_path: Path,
    mock_output_summary_dir_path: Path,
    mock_summary_tsvs: Dict[str, str],
    dt_attr_name: str,
    mock_user_input: str,
    expected_candidate_dt: datetime,
) -> None:
    mock_q_ask = MagicMock()
    mock_q_ask.ask.return_value = mock_user_input
    with patch("questionary.select") as questionary_select_mock:
        questionary_select_mock.return_value = mock_q_ask
        with patch.object(StatsRunPicker, "_get_dt_choices") as mock_get_dt_choices:
            mock_get_dt_choices.return_value = [
                datetime(year=2025, month=2, day=15, hour=1, minute=1, second=59),
                datetime(year=2025, month=2, day=15, hour=1, minute=11, second=25),
            ]
            srp = StatsRunPicker(
                summaries_directory_path=mock_root_summary_dir_path,
                date_str_format=RUN_DATE_STR_FORMAT,
            )
            assert (
                srp._candidate_dt.year == 1970
                and srp._candidate_dt.month == 1
                and srp._candidate_dt.day == 1
                and srp._candidate_dt.hour == 0
                and srp._candidate_dt.minute == 0
                and srp._candidate_dt.second == 0
            )
            actual = srp._prompt_date_component(dt_attr_name=dt_attr_name)
            assert actual == int(mock_user_input)
            assert srp._candidate_dt == expected_candidate_dt


@pytest.mark.parametrize(
    "mock_user_inputs, mock_possible_datetimes, expected, expected_prompt_cnt",
    [
        (
            [
                "2025",
                "4",
                "20",
                "23",
                datetime(year=2025, month=4, day=20, hour=23, minute=59, second=59).strftime(RUN_DATE_STR_FORMAT),
            ],
            [datetime(year=2025, month=4, day=20, hour=23, minute=59, second=59) for _ in range(10)],
            datetime(year=2025, month=4, day=20, hour=23, minute=59, second=59),
            5,
        ),
        (
            ["2025", "4", "20", "23", "59", "59"],
            [datetime(year=2025, month=4, day=20, hour=23, minute=59, second=59) for _ in range(11)],
            datetime(year=2025, month=4, day=20, hour=23, minute=59, second=59),
            6,
        ),
    ],
)
def test_get_run_date_from_user_prompts(
    mock_root_summary_dir_path: Path,
    mock_output_summary_dir_path: Path,
    mock_summary_tsvs: Dict[str, str],
    mock_user_inputs: List[str],
    mock_possible_datetimes: List[List[str]],
    expected: datetime,
    expected_prompt_cnt: int,
) -> None:
    mock_q_ask = MagicMock()
    mock_q_ask.ask.side_effect = mock_user_inputs
    with patch("questionary.select") as questionary_select_mock:
        questionary_select_mock.return_value = mock_q_ask
        srp = StatsRunPicker(
            summaries_directory_path=mock_root_summary_dir_path,
            date_str_format=RUN_DATE_STR_FORMAT,
        )
        srp._possible_datetimes = mock_possible_datetimes
        actual = srp.get_run_date_from_user_prompts()
        assert actual == expected
        actual_prompt_cnt = len(questionary_select_mock.call_args_list)
        assert (
            actual_prompt_cnt == expected_prompt_cnt
        ), f"Expected {expected_prompt_cnt}, but found {actual_prompt_cnt}: {questionary_select_mock.mock_calls}"
