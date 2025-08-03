import re
from typing import Any

import pytest

from plastered.config.field_validators import (
    CLIOverrideSetting,
    _validate_red_pref_val,
    validate_cd_extras_log_value,
    validate_raw_cli_overrides,
    validate_rec_types_to_scrape,
)
from plastered.models.types import EncodingEnum, MediaEnum
from plastered.models.types import FormatEnum


def test_validate_raw_cli_overrides() -> None:
    value = {member.name: "fake-value" for member in CLIOverrideSetting}
    validated_value = validate_raw_cli_overrides(value=value)
    assert validated_value == value


@pytest.mark.parametrize(
    "bad_value, expected_exc_msg",
    [
        ({"not_in_enum": 69}, "Invalid CLI override settings key: 'not_in_enum' is not a valid key."),
        ({CLIOverrideSetting.LFM_API_KEY.name: None}, "CLI override settings value must be non-empty, non-NoneType."),
        ({CLIOverrideSetting.LFM_API_KEY.name: ""}, "CLI override settings value must be non-empty, non-NoneType."),
    ],
)
def test_validate_raw_cli_overrides_raises(bad_value: dict[str, Any], expected_exc_msg: str) -> None:
    with pytest.raises(ValueError, match=re.escape(expected_exc_msg)):
        _ = validate_raw_cli_overrides(value=bad_value)


@pytest.mark.parametrize("valid_value", [-1, 0, 1, 100])
def test_validate_cd_extras_log_value(valid_value: int) -> None:
    validated_value = validate_cd_extras_log_value(valid_value)
    assert validated_value == valid_value


def test_validate_cd_extras_log_value_raises() -> None:
    with pytest.raises(
        ValueError, match=re.escape("cd_only_extras.log values must be one of {0, 1, 100, -1}. Got: 69")
    ):
        _ = validate_cd_extras_log_value(value=69)


@pytest.mark.parametrize(
    "bad_value, exc_msg",
    [
        ([], "rec_types_to_scrape must be a list containing 1 or 2 elements. Got 0 elements."),
        (["a", "b", "c"], "rec_types_to_scrape must be a list containing 1 or 2 elements. Got 3 elements."),
        (["a", "b"], "rec_types_to_scrape may only contain the following possible values"),
    ],
)
def test_validate_rec_types_to_scrape_raises(bad_value: list[str], exc_msg: str) -> None:
    with pytest.raises(ValueError, match=re.escape(exc_msg)):
        _ = validate_rec_types_to_scrape(value=bad_value)


@pytest.mark.parametrize("enum_class", [FormatEnum, MediaEnum, EncodingEnum])
def test_validate_red_pref_val(enum_class: FormatEnum | MediaEnum | EncodingEnum) -> None:
    with pytest.raises(ValueError, match=re.escape("must be one of")):
        _ = _validate_red_pref_val(value="fake", enum_class=enum_class)
