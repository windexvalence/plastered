from plastered.models.adhoc_search_models import AdhocSearch
from plastered.models.search_item import SearchItem


def test_get_matched_mbid_adhoc_prefers_supplied_mbid() -> None:
    si = SearchItem(initial_info=AdhocSearch(artist="Some Artist", release="Some Album", mbid="abc-123"))
    assert si.get_matched_mbid() == "abc-123"


def test_get_matched_mbid_adhoc_without_mbid_or_resolved_info() -> None:
    si = SearchItem(initial_info=AdhocSearch(artist="Some Artist", release="Some Album"))
    assert si.get_matched_mbid() is None


def test_adhoc_search_kwargs_seeded_from_user_fields() -> None:
    si = SearchItem(initial_info=AdhocSearch(artist="Some Artist", release="Some Album", release_year=1996))
    assert si.get_search_kwargs().get("year") == 1996
