import pytest

from plastered.models.musicbrainz_models import MBRelease
from plastered.models.types import RedReleaseType


def _mb_release(primary_type: str | None, secondary_types: tuple[str, ...] = ()) -> MBRelease:
    return MBRelease(
        mbid="m",
        title="t",
        artist="a",
        primary_type=primary_type,
        secondary_types=secondary_types,
        release_date="2020-01-01",
        release_group_mbid="rg",
    )


@pytest.mark.parametrize(
    "primary_type, secondary_types, expected",
    [
        ("Album", (), RedReleaseType.ALBUM),
        ("single", (), RedReleaseType.SINGLE),
        # null / RED-unmapped MB primary-types must fall back to UNKNOWN rather than raising.
        (None, (), RedReleaseType.UNKNOWN),
        ("Other", (), RedReleaseType.UNKNOWN),
        ("Broadcast", (), RedReleaseType.UNKNOWN),
        # RED files compilations / live albums / soundtracks / remixes / ... under their own types.
        ("Album", ("Compilation",), RedReleaseType.COMPILATION),
        ("Album", ("Live",), RedReleaseType.LIVE_ALBUM),
        ("Album", ("Soundtrack",), RedReleaseType.SOUNDTRACK),
        ("Single", ("Remix",), RedReleaseType.REMIX),
        ("Album", ("DJ-mix",), RedReleaseType.DJ_MIX),
        ("Album", ("Mixtape/Street",), RedReleaseType.MIXTAPE),
        ("Album", ("Demo",), RedReleaseType.DEMO),
        ("Album", ("Interview",), RedReleaseType.INTERVIEW),
        (None, ("Compilation",), RedReleaseType.COMPILATION),
        ("Album", ("Audiobook",), RedReleaseType.ALBUM),  # an unmapped secondary type falls back to the primary
    ],
)
def test_get_red_release_type(
    primary_type: str | None, secondary_types: tuple[str, ...], expected: RedReleaseType
) -> None:
    assert _mb_release(primary_type, secondary_types).get_red_release_type() == expected
