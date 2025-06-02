from collections import OrderedDict
from typing import Any, Dict, Optional

import pytest

from plastered.utils.musicbrainz_utils import MBRelease
from plastered.utils.red_utils import RedReleaseType
from tests.conftest import mock_musicbrainz_release_json


@pytest.mark.parametrize(
    "other, expected",
    [
        ("not-right-type", False),
        (
            MBRelease(
                mbid="d211379d-3203-47ed-a0c5-e564815bb45a",
                title="Dr. Octagonecologyst",
                artist="Some-different",
                primary_type="Album",
                first_release_year=1996,
                release_date="2017-05-19",
                label="Get On Down",
                catalog_number="58010",
                release_group_mbid="b38e21f6-8f76-3f87-a021-e91afad9e7e5",
            ),
            False,
        ),
        (
            MBRelease(
                mbid="d211379d-3203-47ed-a0c5-e564815bb45a",
                title="Dr. Octagonecologyst",
                artist="Dr. Octagon",
                primary_type="Album",
                first_release_year=1996,
                release_date="2017-05-19",
                label="Get On Down",
                catalog_number="58010",
                release_group_mbid="b38e21f6-8f76-3f87-a021-e91afad9e7e5",
            ),
            True,
        ),
    ],
)
def test_eq(other: Any, expected: bool) -> None:
    test_instance = MBRelease(
        mbid="d211379d-3203-47ed-a0c5-e564815bb45a",
        title="Dr. Octagonecologyst",
        artist="Dr. Octagon",
        primary_type="Album",
        first_release_year=1996,
        release_date="2017-05-19",
        label="Get On Down",
        catalog_number="58010",
        release_group_mbid="b38e21f6-8f76-3f87-a021-e91afad9e7e5",
    )
    actual = test_instance == other
    assert actual == expected, f"Expected {test_instance}.__eq__(other={other}) to be {expected}, but got {actual}"


def test_construct_from_api(
    mock_musicbrainz_release_json: Dict[str, Any],
    expected_mb_release: MBRelease,
) -> None:
    actual = MBRelease.construct_from_api(json_blob=mock_musicbrainz_release_json)
    assert actual == expected_mb_release
    expected_red_release_type = RedReleaseType.ALBUM
    actual_red_release_type = actual.get_red_release_type()
    assert (
        actual_red_release_type == expected_red_release_type
    ), f"Expected red release type set to '{expected_red_release_type}' but got '{actual_red_release_type}' instead."
    expected_first_release_year = 1996
    actual_first_release_year = actual.get_first_release_year()
    assert actual_first_release_year == expected_first_release_year
    expected_label = "Get On Down"
    actual_label = actual.get_label()
    assert actual_label == expected_label
    expected_catalog_number = "58010"
    actual_catalog_number = actual.get_catalog_number()
    assert actual_catalog_number == expected_catalog_number
    expected_release_url = "https://musicbrainz.org/release/d211379d-3203-47ed-a0c5-e564815bb45a"
    actual_release_url = actual.get_musicbrainz_release_url()
    assert (
        actual_release_url == expected_release_url
    ), f"Unexpected mb release url: '{actual_release_url}'. Expected: '{expected_release_url}'"
    expected_release_group_url = "https://musicbrainz.org/release-group/b38e21f6-8f76-3f87-a021-e91afad9e7e5"
    actual_release_group_url = actual.get_musicbrainz_release_group_url()
    assert (
        actual_release_group_url == expected_release_group_url
    ), f"Unexpected mb release group url: '{actual_release_group_url}'. Expected: '{expected_release_group_url}'"


@pytest.mark.parametrize(
    "raw_field_present, raw_field_value, expected_year",
    [
        (False, "", -1),
        (True, "2017-10-19", 2017),
        (True, "2009", 2009),
        (True, "1995-12", 1995),
    ],
)
def test_release_year_non_match(
    raw_field_present: bool,
    raw_field_value: str,
    expected_year: int,
) -> None:
    release_group_json = {"primary-type": "Single", "id": "fake-rg-mbid"}
    if raw_field_present:
        release_group_json["first-release-date"] = raw_field_value
    mbr = MBRelease.construct_from_api(
        json_blob={
            "id": "fake-mbid",
            "title": "Some Title",
            "artist-credit": [{"name": "Some Artist"}],
            "release-group": release_group_json,
            "date": raw_field_value,
            "label-info": [{"label": {"name": "Some fake label"}, "catalog-number": "1234"}],
        }
    )
    actual_release_year = mbr.get_first_release_year()
    assert (
        actual_release_year == expected_year
    ), f"Expected first_release_year of {expected_year}, but got {actual_release_year} instead."


@pytest.mark.parametrize(
    "primary_type, first_release_year, label, catalog_number, expected",
    [
        (
            "album",
            None,
            None,
            None,
            OrderedDict([("releasetype", 1), ("year", None), ("recordlabel", None), ("cataloguenumber", None)]),
        ),
        (
            "single",
            None,
            None,
            None,
            OrderedDict([("releasetype", 9), ("year", None), ("recordlabel", None), ("cataloguenumber", None)]),
        ),
        (
            "album",
            1969,
            None,
            None,
            OrderedDict([("releasetype", 1), ("year", 1969), ("recordlabel", None), ("cataloguenumber", None)]),
        ),
        (
            "album",
            None,
            "Fake Label",
            None,
            OrderedDict([("releasetype", 1), ("year", None), ("recordlabel", "Fake+Label"), ("cataloguenumber", None)]),
        ),
        (
            "single",
            None,
            None,
            "DOODOO 89",
            OrderedDict([("releasetype", 9), ("year", None), ("recordlabel", None), ("cataloguenumber", "DOODOO+89")]),
        ),
        (
            "album",
            1969,
            "Fake Label",
            "DOODOO 89",
            OrderedDict(
                [("releasetype", 1), ("year", 1969), ("recordlabel", "Fake+Label"), ("cataloguenumber", "DOODOO+89")]
            ),
        ),
    ],
)
def test_get_release_searcher_kwargs(
    primary_type: str,
    first_release_year: Optional[int],
    label: Optional[str],
    catalog_number: Optional[str],
    expected: OrderedDict[str, Any],
) -> None:
    mbr = MBRelease(
        mbid="m",
        title="t",
        artist="a",
        release_date="r",
        release_group_mbid="rgm",
        primary_type=primary_type,
        first_release_year=first_release_year,
        label=label,
        catalog_number=catalog_number,
    )
    actual = mbr.get_release_searcher_kwargs()
    assert isinstance(actual, OrderedDict)
    assert len(actual) == len(expected)
    actual_keys = set(actual.keys())
    expected_keys = set(expected.keys())
    assert actual_keys == expected_keys
    for actual_key, actual_val in actual.items():
        assert actual_val == expected[actual_key]
