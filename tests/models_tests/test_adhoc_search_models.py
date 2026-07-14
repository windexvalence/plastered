import re

import pytest
from pydantic import ValidationError

from plastered.models.adhoc_search_models import AdhocSearch
from plastered.models.types import EntityType, RecContext, RedReleaseType
from plastered.utils.constants import (
    RED_PARAM_CATALOG_NUMBER,
    RED_PARAM_RECORD_LABEL,
    RED_PARAM_RELEASE_TYPE,
    RED_PARAM_RELEASE_YEAR,
)


class TestAdhocSearch:
    def test_requires_release_or_track(self) -> None:
        with pytest.raises(ValidationError, match="at least one of"):
            AdhocSearch(artist="foo")

    def test_requires_non_empty_artist(self) -> None:
        with pytest.raises(ValidationError):
            AdhocSearch(artist="", release="bar")

    @pytest.mark.parametrize(
        "release, track, expected_entity_type, expected_entity",
        [
            ("Some Album", None, EntityType.ALBUM, "Some Album"),
            (None, "Some Track", EntityType.TRACK, "Some Track"),
            # When both are present, the release takes precedence and it is treated as an album search.
            ("Some Album", "Some Track", EntityType.ALBUM, "Some Album"),
        ],
    )
    def test_entity_type_and_entity(
        self, release: str | None, track: str | None, expected_entity_type: EntityType, expected_entity: str
    ) -> None:
        adhoc = AdhocSearch(artist="Some Artist", release=release, track=track)
        assert adhoc.entity_type == expected_entity_type
        assert adhoc.get_human_readable_entity_str() == expected_entity

    def test_human_readable_artist(self) -> None:
        assert AdhocSearch(artist="Fake Artist", release="x").get_human_readable_artist_str() == "Fake Artist"

    def test_encoded_strings(self) -> None:
        adhoc = AdhocSearch(artist="Fake Artist", release="Fake Album")
        assert adhoc.encoded_artist_str == "Fake+Artist"
        assert adhoc.encoded_entity_str == "Fake+Album"

    @pytest.mark.parametrize(
        "release, track, expected_url",
        [
            ("Fake Album", None, "https://www.last.fm/music/Fake+Artist/Fake+Album"),
            (None, "Fake Track", "https://www.last.fm/music/Fake+Artist/_/Fake+Track"),
        ],
    )
    def test_lfm_entity_url(self, release: str | None, track: str | None, expected_url: str) -> None:
        adhoc = AdhocSearch(artist="Fake Artist", release=release, track=track)
        assert adhoc.lfm_entity_url == expected_url

    def test_rec_context(self) -> None:
        assert AdhocSearch(artist="x", release="y").rec_context == RecContext.NOT_SET

    def test_get_human_track_str_for_track(self) -> None:
        assert AdhocSearch(artist="x", track="My Track").get_human_readable_track_str() == "My Track"

    def test_get_human_track_str_for_album_raises(self) -> None:
        with pytest.raises(ValueError, match=re.escape("Cannot get track name from an album ad-hoc search.")):
            AdhocSearch(artist="x", release="My Album").get_human_readable_track_str()

    def test_get_user_search_kwargs_empty_when_unset(self) -> None:
        assert AdhocSearch(artist="x", release="y").get_user_search_kwargs() == {}

    def test_get_user_search_kwargs_all_set(self) -> None:
        adhoc = AdhocSearch(
            artist="x",
            release="y",
            release_type=RedReleaseType.ALBUM,
            release_year=1996,
            record_label="Get On Down",
            catalog_number="58 010",
        )
        kwargs = adhoc.get_user_search_kwargs()
        assert kwargs == {
            RED_PARAM_RELEASE_TYPE: RedReleaseType.ALBUM.value,
            RED_PARAM_RELEASE_YEAR: 1996,
            RED_PARAM_RECORD_LABEL: "Get+On+Down",
            RED_PARAM_CATALOG_NUMBER: "58+010",
        }
