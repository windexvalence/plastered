from typing import Any, Dict, Optional
from unittest.mock import Mock

import pytest
import requests

from lastfm_recs_scraper.utils.musicbrainz_utils import MBRelease
from lastfm_recs_scraper.utils.red_utils import RedReleaseType
from tests.utils_tests.conftest import api_clients_dict, mock_musicbrainz_release_json


@pytest.fixture(scope="session")
def expected_mb_release() -> MBRelease:
    return MBRelease(
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


@pytest.fixture(scope="session")
def mb_client(api_clients_dict: Dict[str, requests.Session]) -> requests.Session:
    return api_clients_dict["musicbrainz"]


def test_construct_from_api(
    mb_client: requests.Session, mock_musicbrainz_release_json: Dict[str, Any], expected_mb_release: MBRelease
) -> None:
    mb_client.get = Mock(name="get")
    mb_client.get.return_value = mock_musicbrainz_release_json
    # TODO: mock client get here
    actual = MBRelease.construct_from_api(musicbrainz_client=mb_client, mbid="d211379d-3203-47ed-a0c5-e564815bb45a")
    assert actual == expected_mb_release
    expected_red_release_type = RedReleaseType.ALBUM
    actual_red_release_type = actual.get_red_release_type()
    assert (
        actual_red_release_type == expected_red_release_type
    ), f"Expected red release type set to '{expected_red_release_type}' but got  '{actual_red_release_type}' instead."
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
    mb_client: requests.Session, raw_field_present: bool, raw_field_value: str, expected_year: int
) -> None:
    mb_client.get = Mock("get")
    release_group_json = {"primary-type": "Single", "id": "fake-rg-mbid"}
    if raw_field_present:
        release_group_json["first-release-date"] = raw_field_value
    mb_client.get.return_value = {
        "id": "fake-mbid",
        "title": "Some Title",
        "artist-credit": [{"name": "Some Artist"}],
        "release-group": release_group_json,
        "date": raw_field_value,
        "label-info": [{"label": {"name": "Some fake label"}, "catalog-number": "1234"}],
    }
    mbr = MBRelease.construct_from_api(musicbrainz_client=mb_client, mbid="fake-mbid")
    actual_release_year = mbr.get_first_release_year()
    assert (
        actual_release_year == expected_year
    ), f"Expected first_release_year of {expected_year}, but got {actual_release_year} instead."
