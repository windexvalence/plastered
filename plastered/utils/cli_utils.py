"""
Contains a few helper decorators / functions to reduce the repeated code in cli.py.
"""

import os
from datetime import datetime
from functools import wraps

import click
import questionary

from plastered.utils.exceptions import StatsRunPickerException

DEFAULT_VERBOSITY = "WARNING"


# Adopted from here to reduce repeat code: https://github.com/pallets/click/issues/108#issuecomment-280489786
def config_path_option(func):
    @click.option(
        "-c",
        "--config",
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


def subcommand_flag(name, help_msg):
    def decorator(func):
        @click.option(name, envvar=None, is_flag=True, default=False, help=help_msg)
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator


# User prompt class, as described in this SO post: https://stackoverflow.com/a/60425679
# Also see this SO answer: https://stackoverflow.com/a/45870325
class StatsRunPicker:
    """
    Helper class for prompting the user to pick a prior run date
    when they've invoked the run_stats CLI command, without passing an explicit --run-date value.
    """

    def __init__(self, summaries_directory_path: str, date_str_format: str):
        self._summaries_directory_path = summaries_directory_path
        self._date_str_format = date_str_format
        self._possible_datetimes = [
            datetime.strptime(dir_name, self._date_str_format)
            for dir_name in os.listdir(self._summaries_directory_path)
            if os.path.isdir(os.path.join(self._summaries_directory_path, dir_name))
        ]
        if len(self._possible_datetimes) == 0:
            raise StatsRunPickerException("No run summary directories found.")
        self._candidate_dt = datetime(year=1970, month=1, day=1)

    def _is_valid_candidate_dt(self, dt: datetime, dt_attr_name: str) -> bool:
        dt_attr_to_filter_fns = {
            "month": lambda dt: dt.year == self._candidate_dt.year,
            "day": lambda dt: dt.year == self._candidate_dt.year and dt.month == self._candidate_dt.month,
            "hour": lambda dt: dt.year == self._candidate_dt.year
            and dt.month == self._candidate_dt.month
            and dt.day == self._candidate_dt.day,
            "minute": lambda dt: dt.year == self._candidate_dt.year
            and dt.month == self._candidate_dt.month
            and dt.day == self._candidate_dt.day
            and dt.hour == self._candidate_dt.hour,
            "second": lambda dt: dt.year == self._candidate_dt.year
            and dt.month == self._candidate_dt.month
            and dt.day == self._candidate_dt.day
            and dt.hour == self._candidate_dt.hour
            and dt.minute == self._candidate_dt.minute,
        }
        filter_fn = dt_attr_to_filter_fns[dt_attr_name]
        return filter_fn(dt)

    def _get_dt_choices(self, dt_attr_name: str) -> list[str]:
        if dt_attr_name == "year":
            return sorted(set([str(dt.__getattribute__(dt_attr_name)) for dt in self._possible_datetimes]))
        return sorted(
            set(
                [
                    str(dt.__getattribute__(dt_attr_name))
                    for dt in self._possible_datetimes
                    if self._is_valid_candidate_dt(dt=dt, dt_attr_name=dt_attr_name)
                ]
            ),
            key=lambda x: int(x),  # pylint: disable=unnecessary-lambda
        )

    def _prompt_date_component(self, dt_attr_name: str) -> int:
        user_input = int(
            questionary.select(
                f"Desired run date {dt_attr_name}?", choices=self._get_dt_choices(dt_attr_name=dt_attr_name)
            ).ask()
        )
        self._candidate_dt = self._candidate_dt.replace(**{dt_attr_name: user_input})  # type: ignore
        return user_input

    def get_run_date_from_user_prompts(self) -> datetime:
        input_year = self._prompt_date_component(dt_attr_name="year")
        input_month = self._prompt_date_component(dt_attr_name="month")
        input_day = self._prompt_date_component(dt_attr_name="day")
        input_hour = self._prompt_date_component(dt_attr_name="hour")
        candidate_run_dts = [
            dt
            for dt in self._possible_datetimes
            if (dt.year == input_year and dt.month == input_month and dt.day == input_day and dt.hour == input_hour)
        ]
        if len(candidate_run_dts) <= 10:
            final_date_str = questionary.select(
                "Choose the run date:",
                choices=sorted([dt.strftime(format=self._date_str_format) for dt in candidate_run_dts]),
            ).ask()
            return datetime.strptime(final_date_str, self._date_str_format)
        input_minute = self._prompt_date_component(dt_attr_name="minute")
        input_second = self._prompt_date_component(dt_attr_name="second")
        return datetime(
            year=input_year, month=input_month, day=input_day, hour=input_hour, minute=input_minute, second=input_second
        )


def prompt_user_for_run_date(summaries_directory_path: str, date_str_format: str) -> datetime:
    """Creates a temporary StatsRunPicker instance and prompts the user for the run date."""
    return StatsRunPicker(
        summaries_directory_path=summaries_directory_path, date_str_format=date_str_format
    ).get_run_date_from_user_prompts()
