import pytest

from plastered.utils.text_utils import same_name


@pytest.mark.parametrize(
    "first, second, expected",
    [
        ("Some Album", "some album!", True),
        ("Café & Bar", "cafe and bar", True),
        ("Some Album", "Some Albums", False),
        ("†", "†", True),  # symbol-only names normalize to "" and fall back to a direct comparison
        ("†", "‡", False),
        ("†", "Some Album", False),
    ],
)
def test_same_name(first: str, second: str, expected: bool) -> None:
    assert same_name(first, second) is expected
