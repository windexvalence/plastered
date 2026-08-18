from plastered.models.adhoc_search_models import AdhocSearch
from plastered.models.lfm_models import LFMAlbumInfo
from plastered.models.musicbrainz_models import MBRelease
from plastered.models.search_item import SearchItem


def _mb_release(mbid: str) -> MBRelease:
    return MBRelease(
        mbid=mbid, title="t", artist="a", primary_type="Album", release_date="2020-01-01", release_group_mbid="rg"
    )


def test_get_matched_mbid_adhoc_prefers_supplied_mbid() -> None:
    si = SearchItem(initial_info=AdhocSearch(artist="Some Artist", release="Some Album", mbid="abc-123"))
    assert si.get_matched_mbid() == "abc-123"


def test_get_matched_mbid_adhoc_without_mbid_or_resolved_info() -> None:
    si = SearchItem(initial_info=AdhocSearch(artist="Some Artist", release="Some Album"))
    assert si.get_matched_mbid() is None


def test_get_matched_mbid_falls_back_to_mb_release() -> None:
    """An item resolved via the MB release search (no LFM MBID) reports the searched release's MBID as matched."""
    si = SearchItem(initial_info=AdhocSearch(artist="Some Artist", release="Some Album"))
    si.set_mb_release(_mb_release(mbid="searched-mbid"))
    assert si.get_matched_mbid() == "searched-mbid"


def test_get_matched_mbid_prefers_lfm_album_mbid_over_mb_release() -> None:
    si = SearchItem(initial_info=AdhocSearch(artist="Some Artist", release="Some Album"))
    si.set_lfm_album_info(LFMAlbumInfo(artist="a", album_name="b", lfm_url="u", release_mbid="lfm-mbid"))
    si.set_mb_release(_mb_release(mbid="searched-mbid"))
    assert si.get_matched_mbid() == "lfm-mbid"


def test_get_matched_mbid_mbidless_lfm_album_info_falls_through_to_mb_release() -> None:
    si = SearchItem(initial_info=AdhocSearch(artist="Some Artist", release="Some Album"))
    si.set_lfm_album_info(LFMAlbumInfo(artist="a", album_name="b", lfm_url="u", release_mbid=None))
    si.set_mb_release(_mb_release(mbid="searched-mbid"))
    assert si.get_matched_mbid() == "searched-mbid"


def test_adhoc_search_kwargs_seeded_from_user_fields() -> None:
    si = SearchItem(initial_info=AdhocSearch(artist="Some Artist", release="Some Album", release_year=1996))
    assert si.get_search_kwargs().get("year") == 1996
