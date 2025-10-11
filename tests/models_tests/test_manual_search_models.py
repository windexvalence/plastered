import re

import pytest

from plastered.models.manual_search_models import ManualSearch
from plastered.models.types import EntityType, RecContext


class TestManualSearch:
    @pytest.mark.parametrize("entity_type", [member for member in EntityType])
    @pytest.mark.parametrize("mbid", [None, "abcd69420"])
    def test_init(self, entity_type: EntityType, mbid: str | None) -> None:
        ms = ManualSearch(entity_type=entity_type, artist="foo", entity="bar", mbid=mbid)
        assert isinstance(ms, ManualSearch)

    @pytest.mark.parametrize(
        "entity_type, entity, expected",
        [(EntityType.ALBUM, "Fake Album", "Fake Album"), (EntityType.TRACK, "Fake Track", "Fake Track")],
    )
    def test_get_human_readable_release_str(self, entity_type: EntityType, entity: str, expected: str) -> None:
        ms = ManualSearch(entity_type=entity_type, entity=entity, artist="Fake Artist")
        actual = ms.get_human_readable_release_str()
        assert actual == expected

    @pytest.mark.parametrize("entity_type", [EntityType.ALBUM, EntityType.TRACK])
    def test_get_human_artist_str(self, entity_type: EntityType) -> None:
        mock_artist = "Fake Artist"
        ms = ManualSearch(entity_type=entity_type, entity="Fake Name", artist=mock_artist)
        actual = ms.get_human_readable_artist_str()
        assert actual == mock_artist

    @pytest.mark.parametrize(
        "entity_type, expected_exc, expected_msg",
        [(EntityType.ALBUM, ValueError, "Cannot get track name from Album entity"), (EntityType.TRACK, None, None)],
    )
    def test_get_human_track_str(
        self, entity_type: EntityType, expected_exc: type[ValueError] | None, expected_msg: str | None
    ) -> None:
        mock_entity_name = "Fake Name"
        ms = ManualSearch(entity_type=entity_type, entity="Fake Name", artist=mock_entity_name)
        if expected_exc is not None:
            with pytest.raises(expected_exc, match=re.escape("Cannot get track name from Album entity")):
                _ = ms.get_human_readable_track_str()
        else:
            actual = ms.get_human_readable_track_str()
            assert actual == mock_entity_name

    @pytest.mark.parametrize(
        "entity_type, expected",
        [
            (EntityType.ALBUM, "https://www.last.fm/music/Fake+Artist/Fake+Name"),
            (EntityType.TRACK, "https://www.last.fm/music/Fake+Artist/_/Fake+Name"),
        ],
    )
    def test_lfm_entity_url(self, entity_type: EntityType, expected: str) -> None:
        mock_artist = "Fake Artist"
        mock_entity = "Fake Name"
        ms = ManualSearch(entity_type=entity_type, artist=mock_artist, entity=mock_entity)
        actual = ms.lfm_entity_url
        assert actual == expected

    @pytest.mark.parametrize("entity_type", [member for member in EntityType])
    def test_rec_context(self, entity_type: EntityType) -> None:
        ms = ManualSearch(entity_type=entity_type, artist="Fake Artist", entity="Fake Name")
        assert ms.rec_context == RecContext.NOT_SET

    @pytest.mark.parametrize("entity_type", [member for member in EntityType])
    def test_get_human_readable_entity_str(self, entity_type: EntityType) -> None:
        ms = ManualSearch(entity_type=entity_type, artist="Fake Artist", entity="Fake Name")
        assert ms.get_human_readable_entity_str() == ms.entity
