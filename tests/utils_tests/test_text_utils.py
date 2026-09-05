import pytest

from plastered.utils.text_utils import featured_artists, same_name, strip_title_suffixes


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


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Song (feat. X)", "Song"),
        ("Song [Live]", "Song"),
        ("Song - Remastered 2011", "Song"),
        ("Song \u2013 Live", "Song"),
        ("Song feat. X", "Song"),
        ("Song ft X", "Song"),
        ("Song Featuring X", "Song"),
        ("Song (feat. X) - 2011 Remaster [Explicit]", "Song"),  # decorations are stripped repeatedly
        ("Song (feat.X)", "Song"),
        ("Song feat.X", "Song"),
        ("Song\u2014Live", "Song"),  # an unspaced em / en dash separates a suffix
        ("Song \u2013Live", "Song"),
        ("(Don't Fear) The Reaper", "(Don't Fear) The Reaper"),  # a leading bracketed group is kept
        ("Re-Animator", "Re-Animator"),  # a hyphenated word is not a dash-separated suffix
        ("Plain", "Plain"),
        (" Song ", "Song"),
        ("(Untitled)", "(Untitled)"),  # stripping would leave nothing: the title stands
        ("(Nice Dream) - Remastered", "(Nice Dream)"),  # a fully bracketed title keeps its bracketed core
        ("(Intro) (Live)", "(Intro)"),
    ],
)
def test_strip_title_suffixes(title: str, expected: str) -> None:
    assert strip_title_suffixes(title) == expected


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Song (feat. X)", ("X",)),
        ("Song (feat.X)", ("X",)),
        ("Song ft.X", ("X",)),
        # A multi-name segment is returned whole (it may be one band) and split.
        ("Song feat. X & Y", ("X & Y", "X", "Y")),
        ("Song (feat. Chase & Status)", ("Chase & Status", "Chase", "Status")),
        ("Song (ft. X, Y and Z) [Live]", ("X, Y and Z", "X", "Y", "Z")),
        ("Song Featuring X + Y - Live", ("X + Y", "X", "Y")),
        ("Song (feat. X) (feat. Y)", ("X", "Y")),
        ("Plain", ()),
        ("Shift Happens", ()),  # "ft" inside a word is not a marker
        ("feat. X", ()),  # a marker MUST follow whitespace or an opening bracket
    ],
)
def test_featured_artists(title: str, expected: tuple[str, ...]) -> None:
    assert featured_artists(title) == expected
