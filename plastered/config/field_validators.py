"""
Various field validator definitions for the Pydantic models representing
the `plastered` application config. For more on Pydantic field validators, see the link below:
https://docs.pydantic.dev/latest/concepts/validators/#field-validators
"""
from enum import unique, IntEnum
from typing import Annotated

from pydantic import AfterValidator

from plastered.utils.red_utils import EncodingEnum, FormatEnum, MediaEnum



@unique
class APIRetries(IntEnum):
    """Enum of API retries settings bounds"""
    DEFAULT = 3
    MIN = 1
    MAX = 10


@unique
class NonRedCallWait(IntEnum):
    """Enum of settings bounds for seconds to wait between API calls for non-RED APIs."""
    DEFAULT = 2
    MIN = 1
    MAX = 6


@unique
class RedCallWait(IntEnum):
    """Enum of settings bounds for seconds to wait between RED API calls."""
    DEFAULT = 5
    MIN = 2
    MAX = 10


def validate_cd_extras_log_value(value: int) -> int:
    """Validates the config value of `cd_only_extras.log` for a red format entry."""
    allowed_values = {-1, 0, 1, 100}
    if value in allowed_values:
        return value
    raise ValueError(f"`cd_only_extras.log` values must be one of {allowed_values}. Got: {value}")


def validate_rec_types_to_scrape(value: list[str]) -> list[str]:
    """Validates the config value for `lfm.rec_types_to_scrape`."""
    val_len = len(value)
    if val_len == 0 or val_len > 2:
        raise ValueError(f"`rec_types_to_scrape` must be a list containing 1 or 2 elements. Got {val_len} elements.")
    allowed_values = {"album", "track"}
    for elem in value:
        if elem not in allowed_values:
            raise ValueError(
                f"`rec_types_to_scrape` may only contain the following possible values: {allowed_values}. Got {value}."
            )
    return value


# Red Format Preferences config validators
def _validate_red_pref_val(value: str, enum_class: FormatEnum | MediaEnum | EncodingEnum) -> str:
    """
    General base validator function for format_preferences.preference entries which must be in a
    specific enum's member values.
    """
    field_name = enum_class.__name__.lower().removesuffix("enum")
    allowed_values = set([member.value for member in enum_class])
    if value not in allowed_values:
        raise ValueError(f"preference.{field_name} must be one of: {allowed_values}")
    return value


ValidRedEncoding = Annotated[str, AfterValidator(lambda v: _validate_red_pref_val(value=v, enum_class=EncodingEnum))]
ValidRedFormat = Annotated[str, AfterValidator(lambda v: _validate_red_pref_val(value=v, enum_class=FormatEnum))]
ValidRedMedia = Annotated[str, AfterValidator(lambda v: _validate_red_pref_val(value=v, enum_class=MediaEnum))]

