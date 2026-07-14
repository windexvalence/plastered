import pytest

from plastered.models.musicbrainz_models import MBRelease
from plastered.models.types import RedReleaseType


def _mb_release(primary_type: str | None) -> MBRelease:
    return MBRelease(
        mbid="m", title="t", artist="a", primary_type=primary_type, release_date="2020-01-01", release_group_mbid="rg"
    )


@pytest.mark.parametrize(
    "primary_type, expected",
    [
        ("Album", RedReleaseType.ALBUM),
        ("single", RedReleaseType.SINGLE),
        # null / RED-unmapped MB primary-types must fall back to UNKNOWN rather than raising.
        (None, RedReleaseType.UNKNOWN),
        ("Other", RedReleaseType.UNKNOWN),
        ("Broadcast", RedReleaseType.UNKNOWN),
    ],
)
def test_get_red_release_type(primary_type: str | None, expected: RedReleaseType) -> None:
    assert _mb_release(primary_type).get_red_release_type() == expected
