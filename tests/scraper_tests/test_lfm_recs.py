from typing import Any

import pytest

from plastered.models.types import RecContext, EntityType
from plastered.models.lfm_models import LFMRec
from plastered.utils.exceptions import LFMRecException


@pytest.mark.parametrize(
    "lfm_rec, expected",
    [
        (
            LFMRec(
                lfm_artist_str="Some+Bad+Artist",
                lfm_entity_str="Some+Dumb+Album",
                recommendation_type=EntityType.ALBUM,
                rec_context=RecContext.SIMILAR_ARTIST,
            ),
            "artist=Some+Bad+Artist, album=Some+Dumb+Album, context=similar-artist",
        ),
        (
            LFMRec(
                lfm_artist_str="Some+Other+Bad+Artist",
                lfm_entity_str="Some+Dumb+Track",
                recommendation_type=EntityType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            "artist=Some+Other+Bad+Artist, track=Some+Dumb+Track, context=in-library",
        ),
    ],
)
def test_lfmrec_str(lfm_rec: LFMRec, expected: str) -> None:
    actual = lfm_rec.__str__()
    assert actual == expected, f"Expected __str__() result to be '{expected}', but got '{actual}'"


@pytest.mark.parametrize(
    "lfm_str, expected",
    [
        ("", ""),
        ("Singleword", "Singleword"),
        ("lowercase", "lowercase"),
        ("Aphex+Twin", "Aphex Twin"),
        ("Aphex Twin", "Aphex Twin"),
        ("Double+Nickels+On+The+Dime", "Double Nickels On The Dime"),
        ("Dr.+Octagonecologyst", "Dr. Octagonecologyst"),
        ("Much+Against+Everyone%27s+Advice", "Much Against Everyone's Advice"),
        ("Signals,+Calls+and+Marches", "Signals, Calls and Marches"),
        ("This+Nation%27s+Saving+Grace", "This Nation's Saving Grace"),
        ("500%25+More+Man", "500% More Man"),
        ("MM...FOOD", "MM...FOOD"),
        ("Chomp+(Remastered)", "Chomp (Remastered)"),
        ("Lying+%2f+a+Wooden+Box", "Lying / a Wooden Box"),
        ("Y", "Y"),
        ("Frankjavcee+Collection,+Vol.+1,+pt.+II", "Frankjavcee Collection, Vol. 1, pt. II"),
        ("Public+Image+LTD.", "Public Image LTD."),
    ],
)
def test_get_human_readable_artist_str(lfm_str: str, expected: str) -> None:
    test_lfm_rec = LFMRec(
        lfm_artist_str=lfm_str,
        lfm_entity_str="Fake+Release",
        recommendation_type=EntityType.ALBUM,
        rec_context=RecContext.SIMILAR_ARTIST,
    )
    actual = test_lfm_rec.get_human_readable_artist_str()
    assert actual == expected, (
        f"Expected LFMRec.get_human_readable_artist_str() to return '{expected}', but got '{actual}'"
    )


@pytest.mark.parametrize("is_track_rec, should_fail, expected", [(False, True, None), (True, False, "Some Entity")])
def test_get_human_readable_track_str(is_track_rec: bool, should_fail: bool, expected: str | None) -> None:
    test_lfm_rec = LFMRec(
        lfm_artist_str="Some+Artist",
        lfm_entity_str="Some+Entity",
        recommendation_type=EntityType.TRACK if is_track_rec else EntityType.ALBUM,
        rec_context=RecContext.IN_LIBRARY,
    )
    if should_fail:
        with pytest.raises(
            LFMRecException, match="Cannot get the track name from an LFMRec instance with a album reccommendation type"
        ):
            test_lfm_rec.get_human_readable_track_str()
    else:
        actual = test_lfm_rec.get_human_readable_track_str()
        assert actual == expected, f"Expected '{expected}', but got '{actual}'"


@pytest.mark.parametrize(
    "lfm_rec, other, expected",
    [
        (
            LFMRec(
                lfm_artist_str="Some+Bad+Artist",
                lfm_entity_str="Some+Dumb+Album",
                recommendation_type=EntityType.ALBUM,
                rec_context=RecContext.SIMILAR_ARTIST,
            ),
            None,
            False,
        ),
        (
            LFMRec(
                lfm_artist_str="Some+Bad+Artist",
                lfm_entity_str="Some+Dumb+Album",
                recommendation_type=EntityType.ALBUM,
                rec_context=RecContext.SIMILAR_ARTIST,
            ),
            LFMRec(
                lfm_artist_str="Some+Other+Bad+Artist",
                lfm_entity_str="Some+Dumb+Track",
                recommendation_type=EntityType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            False,
        ),
        (
            LFMRec(
                lfm_artist_str="Some+Other+Bad+Artist",
                lfm_entity_str="Some+Dumb+Track",
                recommendation_type=EntityType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            LFMRec(
                lfm_artist_str="Some+Other+Bad+Artist",
                lfm_entity_str="Some+Dumb+Track",
                recommendation_type=EntityType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            True,
        ),
    ],
)
def test_lfmrec_eq(lfm_rec: LFMRec, other: Any, expected: bool) -> None:
    actual = lfm_rec.__eq__(other=other)
    assert actual == expected, f"Expected {lfm_rec}.__eq__(other={other}) result to be '{expected}', but got '{actual}'"


@pytest.mark.parametrize(
    "lfm_rec, expected",
    [
        (
            LFMRec(
                lfm_artist_str="Some+Bad+Artist",
                lfm_entity_str="Some+Dumb+Album",
                recommendation_type=EntityType.ALBUM,
                rec_context=RecContext.SIMILAR_ARTIST,
            ),
            False,
        ),
        (
            LFMRec(
                lfm_artist_str="Some+Other+Bad+Artist",
                lfm_entity_str="Some+Dumb+Track",
                recommendation_type=EntityType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            True,
        ),
    ],
)
def test_lfmrec_is_track_rec(lfm_rec: LFMRec, expected: bool) -> None:
    actual = lfm_rec.is_track_rec()
    assert actual == expected, f"Expected {lfm_rec}.is_track_rec to be {expected}, but got {actual}"


@pytest.mark.parametrize(
    "lfm_rec, expected",
    [
        (
            LFMRec(
                lfm_artist_str="Some+Bad+Artist",
                lfm_entity_str="Some+Dumb+Album",
                recommendation_type=EntityType.ALBUM,
                rec_context=RecContext.SIMILAR_ARTIST,
            ),
            "https://www.last.fm/music/Some+Bad+Artist/Some+Dumb+Album",
        ),
        (
            LFMRec(
                lfm_artist_str="Some+Other+Bad+Artist",
                lfm_entity_str="Some+Dumb+Track",
                recommendation_type=EntityType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            "https://www.last.fm/music/Some+Other+Bad+Artist/_/Some+Dumb+Track",
        ),
    ],
)
def test_lfm_entity_url(lfm_rec: LFMRec, expected: str) -> None:
    actual = lfm_rec.lfm_entity_url
    assert actual == expected, f"Expected {lfm_rec}.lfm_entity_url to be '{expected}', but got '{actual}'"
