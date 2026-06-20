import re

import pytest

from plastered.models.types import coerce_to_float_value, coerce_to_gb_value


@pytest.mark.parametrize("raw_value, expected", [("5", 5.0), (6, 6.0)])
def test_coerce_to_float_value(raw_value: str | int, expected: float) -> None:
    actual = coerce_to_float_value(raw_value=raw_value)
    assert actual == expected


@pytest.mark.parametrize("raw_value, expected", [("2000000000", 2.0), (2000000000, 2.0)])
def test_coerce_to_gb_value(raw_value: str | int, expected: float) -> None:
    actual = coerce_to_gb_value(bytes_value=raw_value)
    assert actual == expected


@pytest.mark.parametrize("raw_value", ["-2000000000", -2000000000])
def test_coerce_to_gb_value_negative_raises(raw_value: str | int) -> None:
    with pytest.raises(ValueError, match=re.escape("Cannot be negative")):
        _ = coerce_to_gb_value(bytes_value=raw_value)
