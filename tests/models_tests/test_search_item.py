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


def test_get_matched_mbid_prefers_lfm_album_mbid_until_the_mb_release_resolves() -> None:
    """The LFM MBID drives the lookup; once resolved, the MB release (which replaces a stale MBID) is authoritative."""
    si = SearchItem(initial_info=AdhocSearch(artist="Some Artist", release="Some Album"))
    si.set_lfm_album_info(LFMAlbumInfo(artist="a", album_name="b", lfm_url="u", release_mbid="lfm-mbid"))
    assert si.get_matched_mbid() == "lfm-mbid"
    si.set_mb_release(_mb_release(mbid="resolved-mbid"))
    assert si.get_matched_mbid() == "resolved-mbid"


def test_get_matched_mbid_mbidless_lfm_album_info_falls_through_to_mb_release() -> None:
    si = SearchItem(initial_info=AdhocSearch(artist="Some Artist", release="Some Album"))
    si.set_lfm_album_info(LFMAlbumInfo(artist="a", album_name="b", lfm_url="u", release_mbid=None))
    si.set_mb_release(_mb_release(mbid="searched-mbid"))
    assert si.get_matched_mbid() == "searched-mbid"


def test_adhoc_search_kwargs_seeded_from_user_fields() -> None:
    si = SearchItem(initial_info=AdhocSearch(artist="Some Artist", release="Some Album", release_year=1996))
    assert si.get_search_kwargs().get("year") == 1996


# ---- track items: origin candidates ------------------------------------------------------------------------------

from plastered.models.origin_release import OriginRelease, OriginSource  # noqa: E402
from plastered.models.types import RedReleaseType  # noqa: E402
from plastered.utils.constants import RED_PARAM_RELEASE_TYPE, RED_PARAM_RELEASE_YEAR  # noqa: E402


def _origin(
    name: str, mbid: str | None = None, primary_type: str | None = "Album", date: str | None = "2000"
) -> OriginRelease:
    return OriginRelease(
        release_name=name,
        source=OriginSource.MB_RECORDING_LOOKUP,
        release_mbid=mbid,
        primary_type=primary_type,
        release_date=date,
    )


def _track_si(**adhoc_kwargs) -> SearchItem:
    return SearchItem(initial_info=AdhocSearch(artist="Some Artist", track="Some Track", **adhoc_kwargs))


def test_set_origin_candidates_sets_release_name_and_resets_match() -> None:
    si = _track_si()
    assert si.release_name == "None" and si.top_origin is None
    si.set_matched_origin(_origin("Old"))
    si.set_origin_candidates([_origin("Album"), _origin("Single", primary_type="Single")])
    assert si.release_name == "Album"
    assert si.top_origin == _origin("Album")
    assert si.matched_origin is None


def test_set_origin_candidates_empty_keeps_release_name() -> None:
    si = _track_si()
    si.set_origin_candidates([])
    assert si.release_name == "None" and si.origin_candidates == []


def test_set_matched_origin_updates_release_name() -> None:
    si = _track_si()
    si.set_origin_candidates([_origin("Album"), _origin("Single", primary_type="Single")])
    si.set_matched_origin(si.origin_candidates[1])
    assert si.release_name == "Single" and si.matched_origin == _origin("Single", primary_type="Single")


def test_get_matched_mbid_track_prefers_matched_origin_over_top() -> None:
    si = _track_si()
    si.set_origin_candidates([_origin("Album", mbid="top-mbid"), _origin("Single", mbid="single-mbid")])
    assert si.get_matched_mbid() == "top-mbid"
    si.set_matched_origin(si.origin_candidates[1])
    assert si.get_matched_mbid() == "single-mbid"


def test_get_matched_mbid_track_resolved_mb_release_beats_top_origin_mbid() -> None:
    si = _track_si()
    si.set_origin_candidates([_origin("Album", mbid="stale-mbid"), _origin("Single", mbid="single-mbid")])
    si.set_mb_release(_mb_release(mbid="resolved-mbid"))
    assert si.get_matched_mbid() == "resolved-mbid"
    si.set_matched_origin(si.origin_candidates[0])
    assert si.get_matched_mbid() == "resolved-mbid"
    si.set_matched_origin(si.origin_candidates[1])
    assert si.get_matched_mbid() == "single-mbid"


def test_get_matched_mbid_track_top_without_mbid_falls_back_to_mb_release() -> None:
    si = _track_si()
    si.set_origin_candidates([_origin("Album", mbid=None)])
    si.set_mb_release(_mb_release(mbid="searched-mbid"))
    assert si.get_matched_mbid() == "searched-mbid"


def test_get_matched_mbid_track_non_top_match_without_mbid_is_none() -> None:
    """The MB release describes the top candidate, so it must not be reported for a different matched candidate."""
    si = _track_si()
    si.set_origin_candidates([_origin("Album", mbid=None), _origin("Single", mbid=None)])
    si.set_mb_release(_mb_release(mbid="top-searched-mbid"))
    si.set_matched_origin(si.origin_candidates[1])
    assert si.get_matched_mbid() is None


def test_get_origin_search_kwargs_top_candidate_merges_mb_release_and_own_values() -> None:
    si = _track_si()
    si.set_origin_candidates(
        [_origin("Album", primary_type="Album", date="2005"), _origin("Single", primary_type="Single", date="2006")]
    )
    si.set_mb_release(_mb_release(mbid="m"))  # primary_type Album, first_release_year -1 (unknown)
    top_kwargs = si.get_origin_search_kwargs(origin=si.origin_candidates[0])
    assert (
        top_kwargs[RED_PARAM_RELEASE_TYPE] == RedReleaseType.ALBUM.value and top_kwargs[RED_PARAM_RELEASE_YEAR] == 2005
    )
    assert "recordlabel" in top_kwargs  # MB-resolved (None-valued) keys are carried for the top candidate only
    other_kwargs = si.get_origin_search_kwargs(origin=si.origin_candidates[1])
    assert dict(other_kwargs) == {RED_PARAM_RELEASE_TYPE: RedReleaseType.SINGLE.value, RED_PARAM_RELEASE_YEAR: 2006}


def test_get_origin_search_kwargs_mb_release_values_beat_own_values_for_top_candidate() -> None:
    si = _track_si()
    si.set_origin_candidates([_origin("Album", primary_type="Single", date="2005")])
    mbr = _mb_release(mbid="m")
    mbr.first_release_year = 1999
    si.set_mb_release(mbr)
    kwargs = si.get_origin_search_kwargs(origin=si.origin_candidates[0])
    assert kwargs[RED_PARAM_RELEASE_TYPE] == RedReleaseType.ALBUM.value and kwargs[RED_PARAM_RELEASE_YEAR] == 1999


def test_get_origin_search_kwargs_user_values_win_for_every_candidate() -> None:
    si = _track_si(release_year=1998, release_type=RedReleaseType.SINGLE)
    si.set_origin_candidates([_origin("Album", date="2005"), _origin("Single", primary_type="Single", date="2006")])
    si.set_mb_release(_mb_release(mbid="m"))
    for origin in si.origin_candidates:
        kwargs = si.get_origin_search_kwargs(origin=origin)
        assert kwargs[RED_PARAM_RELEASE_TYPE] == RedReleaseType.SINGLE.value and kwargs[RED_PARAM_RELEASE_YEAR] == 1998


def test_get_origin_search_kwargs_untyped_undated_candidate() -> None:
    si = _track_si()
    si.set_origin_candidates([_origin("Album"), OriginRelease(release_name="LFM Album", source=OriginSource.LFM)])
    assert dict(si.get_origin_search_kwargs(origin=si.origin_candidates[1])) == {}


def test_search_kwargs_has_all_required_fields_track_uses_top_origin() -> None:
    si = _track_si()
    si.set_origin_candidates([_origin("Album", primary_type="Album", date="2005")])
    assert si.search_kwargs_has_all_required_fields({RED_PARAM_RELEASE_TYPE, RED_PARAM_RELEASE_YEAR}) is True
    si.set_origin_candidates([_origin("Album", primary_type=None, date="2005")])
    assert si.search_kwargs_has_all_required_fields({RED_PARAM_RELEASE_TYPE, RED_PARAM_RELEASE_YEAR}) is False
    assert si.search_kwargs_has_all_required_fields({RED_PARAM_RELEASE_YEAR}) is True
