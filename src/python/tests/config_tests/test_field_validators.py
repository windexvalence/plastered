import re

import pytest

from plastered.models.field_validators import validate_cd_extras_log_value, validate_rec_types_to_scrape


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
