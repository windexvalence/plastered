from copy import deepcopy
from pathlib import Path
import re
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from plastered.config.app_settings import AppSettings, get_app_settings
from plastered.db.db_models import FinalState
from plastered.models.lfm_models import LFMAlbumInfo
from plastered.models.manual_search_models import ManualSearch
from plastered.models.red_models import RedFormat, TorrentEntry
from plastered.models.search_item import SearchItem
from plastered.models.types import RedReleaseType
from plastered.release_search.search_helpers import SearchState, _require_mbid_resolution, _required_search_kwargs
from plastered.models.lfm_models import LFMRec
from plastered.models.types import RecContext as rc
from plastered.models.types import EntityType as rt
from plastered.stats.stats import SkippedReason as sr
from plastered.utils.constants import (
    RED_PARAM_CATALOG_NUMBER,
    RED_PARAM_RECORD_LABEL,
    RED_PARAM_RELEASE_TYPE,
    RED_PARAM_RELEASE_YEAR,
)
from plastered.models.lfm_models import LFMTrackInfo
from plastered.models.types import EncodingEnum as ee
from plastered.models.types import FormatEnum as fe
from plastered.models.types import MediaEnum as me
from plastered.models.red_models import RedUserDetails
from plastered.utils.exceptions import SearchItemException, SearchStateException

# TODO: add remainder of SearchState test cases


@pytest.fixture(scope="function")
def mock_torrent_entry() -> TorrentEntry:
    return TorrentEntry(
        torrent_id=69,
        media="WEB",
        format="FLAC",
        encoding="24bit Lossless",
        size=69420,
        scene=False,
        trumpable=False,
        has_snatched=False,
        has_log=False,
        log_score=0,
        has_cue=False,
        can_use_token=False,
        reported=None,
        lossy_web=None,
        lossy_master=None,
    )


@pytest.mark.parametrize(
    "rf, mock_kwargs_user_settings, mock_search_kwargs, expected_browse_params",
    [
        pytest.param(
            RedFormat(format=fe.FLAC, encoding=ee.TWO_FOUR_BIT_LOSSLESS, media=me.WEB),
            {
                "use_release_type": False,
                "use_first_release_year": False,
                "use_record_label": False,
                "use_catalog_number": False,
            },
            {},
            "artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc",
            id="disabled-all-empty-kwargs",
        ),
        pytest.param(
            RedFormat(format=fe.FLAC, encoding=ee.LOSSLESS, media=me.WEB),
            {
                "use_release_type": False,
                "use_first_release_year": False,
                "use_record_label": False,
                "use_catalog_number": False,
            },
            {
                RED_PARAM_RELEASE_TYPE: "foo",
                RED_PARAM_RELEASE_YEAR: 1969,
                RED_PARAM_RECORD_LABEL: "fake",
                RED_PARAM_CATALOG_NUMBER: "bar",
            },
            "artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc",
            id="disabled-all-full-kwargs",
        ),
        pytest.param(
            RedFormat(format=fe.MP3, encoding=ee.MP3_V0, media=me.WEB),
            {
                "use_release_type": True,
                "use_first_release_year": True,
                "use_record_label": True,
                "use_catalog_number": True,
            },
            {},
            "artistname=Some+Artist&groupname=Some+Bad+Album&format=MP3&encoding=V0+(VBR)&media=WEB&group_results=1&order_by=seeders&order_way=desc",
            id="enabled-all-empty-kwargs",
        ),
        pytest.param(
            RedFormat(format=fe.MP3, encoding=ee.MP3_V0, media=me.CD),
            {
                "use_release_type": False,
                "use_first_release_year": True,
                "use_record_label": False,
                "use_catalog_number": False,
            },
            {RED_PARAM_RELEASE_YEAR: 1969},
            "artistname=Some+Artist&groupname=Some+Bad+Album&format=MP3&encoding=V0+(VBR)&media=CD&group_results=1&order_by=seeders&order_way=desc&year=1969",
            id="use-release-year-valid",
        ),
        pytest.param(
            RedFormat(format=fe.FLAC, encoding=ee.TWO_FOUR_BIT_LOSSLESS, media=me.WEB),
            {
                "use_release_type": True,
                "use_first_release_year": False,
                "use_record_label": False,
                "use_catalog_number": False,
            },
            {RED_PARAM_RELEASE_TYPE: RedReleaseType.ALBUM.value},
            "artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc&releasetype=1",
            id="use-release-type-valid",
        ),
        pytest.param(
            RedFormat(format=fe.FLAC, encoding=ee.TWO_FOUR_BIT_LOSSLESS, media=me.WEB),
            {
                "use_release_type": False,
                "use_first_release_year": False,
                "use_record_label": True,
                "use_catalog_number": False,
            },
            {RED_PARAM_RECORD_LABEL: "Fake+Label"},
            "artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc&recordlabel=Fake+Label",
            id="use-record-label-valid",
        ),
        pytest.param(
            RedFormat(format=fe.FLAC, encoding=ee.TWO_FOUR_BIT_LOSSLESS, media=me.WEB),
            {
                "use_release_type": False,
                "use_first_release_year": False,
                "use_record_label": False,
                "use_catalog_number": True,
            },
            {RED_PARAM_CATALOG_NUMBER: "FL+69420"},
            "artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc&cataloguenumber=FL+69420",
            id="use-catalog-num-valid",
        ),
        pytest.param(
            RedFormat(format=fe.FLAC, encoding=ee.TWO_FOUR_BIT_LOSSLESS, media=me.WEB),
            {
                "use_release_type": True,
                "use_first_release_year": True,
                "use_record_label": True,
                "use_catalog_number": True,
            },
            {
                RED_PARAM_RELEASE_TYPE: RedReleaseType.ALBUM.value,
                RED_PARAM_RELEASE_YEAR: 1969,
                RED_PARAM_RECORD_LABEL: "Fake+Label",
                RED_PARAM_CATALOG_NUMBER: "FL+69420",
            },
            "artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc&releasetype=1&year=1969&recordlabel=Fake+Label&cataloguenumber=FL+69420",
            id="use-all-kwargs-valid",
        ),
    ],
)
def test_create_browse_params(
    valid_config_raw_data: dict[str, Any],
    valid_config_filepath: str,
    rf: RedFormat,
    mock_kwargs_user_settings: dict[str, bool],
    mock_search_kwargs: dict[str, Any],
    expected_browse_params: str,
) -> None:
    mock_settings_data = deepcopy(valid_config_raw_data)
    for raw_k, raw_v in mock_kwargs_user_settings.items():
        mock_settings_data["red"]["search"][raw_k] = raw_v
    mock_settings_data["src_yaml_filepath"] = Path(valid_config_filepath)
    with patch("plastered.config.app_settings._get_settings_data", return_value=mock_settings_data):
        app_settings = get_app_settings(src_yaml_filepath=valid_config_filepath)
        search_state = SearchState(app_settings=app_settings)
        si = SearchItem(
            initial_info=LFMRec(
                lfm_artist_str="Some+Artist",
                lfm_entity_str="Some+Bad+Album",
                recommendation_type=rt.ALBUM,
                rec_context=rc.SIMILAR_ARTIST,
            ),
            search_kwargs=mock_search_kwargs,
        )
        actual_browse_params = search_state.create_red_browse_params(red_format=rf, si=si)
        assert actual_browse_params == expected_browse_params, (
            f"Expected browse params to be '{expected_browse_params}', but got '{actual_browse_params}' instead."
        )


@pytest.mark.parametrize(
    "lfm_track_info, expected",
    [(None, False), (LFMTrackInfo("Some Artist", "Track Title", "Source Album", "https://fake-url", "69-420"), True)],
)
def test_post_resolve_track_filter(
    valid_app_settings: AppSettings, lfm_track_info: LFMTrackInfo | None, expected: bool
) -> None:
    search_state = SearchState(app_settings=valid_app_settings)
    search_item = SearchItem(
        initial_info=LFMRec("Some+Artist", "Track+Title", rt.TRACK, rc.SIMILAR_ARTIST), lfm_track_info=lfm_track_info
    )
    actual = search_state.post_resolve_track_filter(si=search_item)
    assert actual == expected


@pytest.mark.parametrize(
    "skip_prior_snatches, mock_has_snatched_release, expected",
    [(False, False, False), (False, True, False), (True, False, False), (True, True, True)],
)
def test_pre_search_rule_skip_prior_snatch(
    valid_app_settings: AppSettings, skip_prior_snatches: bool, mock_has_snatched_release: bool, expected: bool
) -> None:
    si = SearchItem(initial_info=LFMRec("a", "e", rt.ALBUM, rc.SIMILAR_ARTIST))
    search_state = SearchState(app_settings=valid_app_settings)
    search_state._red_user_details = MagicMock(
        name="_red_user_details.has_snatched_release", create=True, return_value=mock_has_snatched_release
    )
    search_state._red_user_details.has_snatched_release.return_value = mock_has_snatched_release
    search_state._skip_prior_snatches = skip_prior_snatches
    actual = search_state._pre_search_rule_skip_prior_snatch(si=si)
    assert actual == expected


def test_pre_search_rule_skip_prior_snatch_user_details_not_initialized(valid_app_settings: AppSettings) -> None:
    si = SearchItem(initial_info=LFMRec("a", "e", rt.ALBUM, rc.SIMILAR_ARTIST))
    search_state = SearchState(app_settings=valid_app_settings)
    search_state._red_user_details = None
    with pytest.raises(SearchStateException, match=re.escape("Red User Details not initialized")):
        _ = search_state._pre_search_rule_skip_prior_snatch(si=si)


@pytest.mark.parametrize(
    "allow_library_items, rec_context, expected",
    [
        (False, rc.SIMILAR_ARTIST, False),
        (False, rc.IN_LIBRARY, True),
        (True, rc.SIMILAR_ARTIST, False),
        (True, rc.IN_LIBRARY, False),
    ],
)
def test_pre_search_rule_skip_library_items(
    valid_app_settings: AppSettings, allow_library_items: bool, rec_context: rc, expected: bool
) -> None:
    si = SearchItem(initial_info=LFMRec("a", "e", rt.ALBUM, rec_context))
    search_state = SearchState(app_settings=valid_app_settings)
    search_state._allow_library_items = allow_library_items
    actual = search_state._pre_search_rule_skip_library_items(si=si)
    assert actual == expected


@pytest.mark.parametrize(
    "rec_context, mock_rule_skip_prior_snatch, mock_rule_skip_library_items, expected, expected_reason",
    [
        (rc.SIMILAR_ARTIST, False, False, True, None),
        (rc.IN_LIBRARY, True, False, False, sr.ALREADY_SNATCHED),
        (rc.SIMILAR_ARTIST, False, False, True, None),
        (rc.IN_LIBRARY, False, True, False, sr.REC_CONTEXT_FILTERING),
    ],
)
def test_pre_search_filter(
    valid_app_settings: AppSettings,
    rec_context: rc,
    mock_rule_skip_prior_snatch: bool,
    mock_rule_skip_library_items: bool,
    expected: bool,
    expected_reason: sr | None,
) -> None:
    si = SearchItem(initial_info=LFMRec("a", "e", rt.ALBUM, rec_context))
    with patch.object(SearchState, "_pre_search_rule_skip_prior_snatch", return_value=mock_rule_skip_prior_snatch):
        with patch.object(
            SearchState, "_add_skipped_snatch_row", return_value=mock_rule_skip_library_items
        ) as mock_add_skipped_snatch_row:
            search_state = SearchState(app_settings=valid_app_settings)
            actual = search_state.pre_mbid_resolution_filter(si=si)
            assert actual == expected
            if expected:
                mock_add_skipped_snatch_row.assert_not_called()
            else:
                mock_add_skipped_snatch_row.assert_called_once_with(si=si, reason=expected_reason)


@pytest.mark.parametrize(
    "mock_require_mbid_resolution, mock_has_all_required_fields, expected, expected_add_row_call_cnt",
    [(False, False, True, 0), (True, False, False, 1), (True, True, True, 0)],
)
def test_post_mbid_resolution_filter(
    valid_app_settings: AppSettings,
    mock_require_mbid_resolution: bool,
    mock_has_all_required_fields: bool,
    expected: bool,
    expected_add_row_call_cnt: int,
) -> None:
    test_si = SearchItem(initial_info=LFMRec("a", "e", rt.ALBUM, rc.IN_LIBRARY))
    with (
        patch.object(SearchItem, "search_kwargs_has_all_required_fields", return_value=mock_has_all_required_fields),
        patch.object(SearchState, "_add_skipped_snatch_row", return_value=None) as mock_add_skipped_snatch_row,
    ):
        search_state = SearchState(app_settings=valid_app_settings)
        search_state._require_mbid_resolution = mock_require_mbid_resolution
        actual = search_state.post_mbid_resolution_filter(si=test_si)
        assert actual == expected
        assert len(mock_add_skipped_snatch_row.mock_calls) == expected_add_row_call_cnt


@pytest.mark.parametrize(
    "mock_tids_to_snatch, mock_pre_snatched, expected, expected_reason",
    [([], False, False, None), ([69], False, True, sr.DUPE_OF_ANOTHER_REC), ([], True, True, sr.ALREADY_SNATCHED)],
)
def test_post_search_rule_dupe_snatch(
    valid_app_settings: AppSettings,
    mock_torrent_entry: TorrentEntry,
    no_snatch_user_details: RedUserDetails,
    mock_tids_to_snatch: set[int],
    mock_pre_snatched: bool,
    expected: bool,
    expected_reason: sr | None,
) -> None:
    with (
        patch.object(SearchState, "_add_skipped_snatch_row") as mock_add_skipped_snatch_row,
        patch.object(RedUserDetails, "has_snatched_tid", return_value=mock_pre_snatched),
    ):
        si = SearchItem(initial_info=LFMRec("a", "e", rt.ALBUM, rc.SIMILAR_ARTIST))
        si.torrent_entry = mock_torrent_entry
        search_state = SearchState(app_settings=valid_app_settings)
        search_state._tids_to_snatch = mock_tids_to_snatch
        search_state._red_user_details = no_snatch_user_details
        actual = search_state._post_search_rule_dupe_snatch(si=si)
        assert actual == expected
        if expected:
            mock_add_skipped_snatch_row.assert_called_once_with(si=si, reason=expected_reason)
        else:
            mock_add_skipped_snatch_row.assert_not_called()


def test_post_search_rule_dupe_snatch_user_details_not_initialized(valid_app_settings: AppSettings) -> None:
    si = SearchItem(initial_info=LFMRec("a", "e", rt.ALBUM, rc.SIMILAR_ARTIST))
    search_state = SearchState(app_settings=valid_app_settings)
    search_state._red_user_details = None
    with pytest.raises(SearchStateException, match=re.escape("Red user details not initialized")):
        _ = search_state._post_search_rule_dupe_snatch(si=si)


def test_post_search_rule_dupe_snatch_no_torrent_entry(
    valid_app_settings: AppSettings, no_snatch_user_details: RedUserDetails
) -> None:
    si = SearchItem(initial_info=LFMRec("a", "e", rt.ALBUM, rc.SIMILAR_ARTIST), torrent_entry=None)
    search_state = SearchState(app_settings=valid_app_settings)
    search_state._red_user_details = no_snatch_user_details
    with pytest.raises(SearchItemException, match=re.escape("SearchItem instance has not torrent_entry")):
        _ = search_state._post_search_rule_dupe_snatch(si=si)


def test_post_search_filter_no_red_match(valid_app_settings: AppSettings) -> None:
    si = SearchItem(initial_info=LFMRec("a", "e", rt.ALBUM, rc.SIMILAR_ARTIST))
    with patch.object(SearchState, "_add_skipped_snatch_row") as mock_add_skipped_snatch_row:
        search_state = SearchState(app_settings=valid_app_settings)
        actual = search_state.post_red_search_filter(si=si)
        assert actual == False
        mock_add_skipped_snatch_row.assert_called_once_with(si=si, reason=sr.NO_MATCH_FOUND)


def test_post_search_filter_above_max_size(valid_app_settings: AppSettings, mock_torrent_entry: TorrentEntry) -> None:
    si = SearchItem(
        initial_info=LFMRec("a", "e", rt.ALBUM, rc.SIMILAR_ARTIST),
        above_max_size_te_found=True,
        torrent_entry=mock_torrent_entry,
    )
    with patch.object(SearchState, "_add_skipped_snatch_row") as mock_add_skipped_snatch_row:
        search_state = SearchState(app_settings=valid_app_settings)
        actual = search_state.post_red_search_filter(si=si)
        assert actual == False
        mock_add_skipped_snatch_row.assert_called_once_with(si=si, reason=sr.ABOVE_MAX_SIZE)


@pytest.mark.parametrize("mock_rule_dupe_snatch_res, expected", [(False, True), (True, False)])
def test_post_search_filter_dupe_snatch(
    valid_app_settings: AppSettings, mock_rule_dupe_snatch_res: bool, expected: bool
) -> None:
    si = SearchItem(
        initial_info=LFMRec("a", "e", rt.ALBUM, rc.SIMILAR_ARTIST),
        above_max_size_te_found=False,
        torrent_entry=mock_torrent_entry,
    )
    with patch.object(
        SearchState, "_post_search_rule_dupe_snatch", return_value=mock_rule_dupe_snatch_res
    ) as mock_rule_dupe_fn:
        search_state = SearchState(app_settings=valid_app_settings)
        actual = search_state.post_red_search_filter(si=si)
        assert actual == expected
        mock_rule_dupe_fn.assert_called_once_with(si=si)


@pytest.mark.parametrize("mock_exc_name", [None, "FakeException"])
def test_add_snatch_final_status_row(
    valid_app_settings: AppSettings, mock_torrent_entry: TorrentEntry, mock_exc_name: str
) -> None:
    si = SearchItem(initial_info=LFMRec("a", "e", rt.ALBUM, rc.SIMILAR_ARTIST))
    si.torrent_entry = mock_torrent_entry
    with (
        patch.object(SearchState, "_add_failed_snatch_row") as mock_add_failed_snatch_row,
        patch.object(SearchState, "_add_snatch_success_row") as mock_add_snatch_success_row,
        patch.object(SearchState, "_update_run_dl_total") as mock_update_run_dl_total,
    ):
        search_state = SearchState(app_settings=valid_app_settings)
        search_state.add_snatch_final_status_row(
            si=si, snatched_with_fl=True, snatch_path="/fake/path", exc_name=mock_exc_name
        )
        if mock_exc_name:
            mock_add_failed_snatch_row.assert_called_once_with(si=si, exc_name=mock_exc_name)
            mock_add_snatch_success_row.assert_not_called()
            mock_update_run_dl_total.assert_not_called()
        else:
            mock_add_failed_snatch_row.assert_not_called()
            mock_add_snatch_success_row.assert_called_once_with(si=si, snatch_path="/fake/path", snatched_with_fl=True)
            mock_update_run_dl_total.assert_called_once_with(te=si.torrent_entry)


def test_add_search_item_to_snatch(valid_app_settings: AppSettings, mock_torrent_entry: TorrentEntry) -> None:
    si = SearchItem(
        initial_info=LFMRec("a", "e", rt.ALBUM, rc.SIMILAR_ARTIST),
        above_max_size_te_found=False,
        torrent_entry=mock_torrent_entry,
    )
    search_state = SearchState(app_settings=valid_app_settings)
    assert len(search_state._search_items_to_snatch) == 0, (
        "Expect initial search state to have 0 items in to_snatch list"
    )
    assert len(search_state._tids_to_snatch) == 0, "Expect initial search state to have 0 items in _tids_to_snatch"
    search_state.add_search_item_to_snatch(si=si)
    assert search_state._search_items_to_snatch == [si]
    assert search_state._tids_to_snatch == set([si.torrent_entry.torrent_id])


def test_get_search_items_to_snatch_hit_size_limit(
    valid_app_settings: AppSettings, mock_torrent_entry: TorrentEntry
) -> None:
    mock_items_to_snatch = [
        SearchItem(
            initial_info=LFMRec("a", "e", rt.ALBUM, rc.SIMILAR_ARTIST),
            above_max_size_te_found=False,
            torrent_entry=mock_torrent_entry,
        )
    ]
    expected = []
    with patch.object(SearchState, "_add_skipped_snatch_row") as mock_add_skipped_snatch_row_fn:
        search_state = SearchState(app_settings=valid_app_settings)
        search_state._max_download_allowed_gb = mock_torrent_entry.get_size("GB") / 2.0
        search_state._search_items_to_snatch = mock_items_to_snatch
        actual = search_state.get_search_items_to_snatch()
        assert actual == expected
        mock_add_skipped_snatch_row_fn.assert_called_once_with(si=mock_items_to_snatch[0], reason=sr.MIN_RATIO_LIMIT)


def test_get_search_items_to_snatch_manual_run(valid_app_settings: AppSettings) -> None:
    search_state = SearchState(app_settings=valid_app_settings)
    mock_si = SearchItem(initial_info=ManualSearch(entity_type=rt.ALBUM, artist="fake", entity="faker"))
    search_state._manual_search_item_to_snatch = mock_si
    actual = search_state.get_search_items_to_snatch(manual_run=True)
    assert isinstance(actual, list)
    assert len(actual) == 1
    assert actual[0] is mock_si


def test_get_search_items_to_snatch_manual_run_none(valid_app_settings: AppSettings) -> None:
    search_state = SearchState(app_settings=valid_app_settings)
    search_state._manual_search_item_to_snatch = None
    actual = search_state.get_search_items_to_snatch(manual_run=True)
    assert isinstance(actual, list)
    assert len(actual) == 0


@pytest.mark.parametrize(
    "use_release_type, use_first_release_year, use_record_label, use_catalog_number, expected",
    [
        (False, False, False, False, False),
        (False, False, False, True, True),
        (False, False, True, False, True),
        (False, True, False, False, True),
        (True, False, False, False, True),
        (True, False, False, True, True),
        (True, False, True, False, True),
        (True, True, False, False, True),
        (True, True, False, True, True),
        (True, True, True, False, True),
        (True, True, True, True, True),
    ],
)
def test_require_mbid_resolution(
    use_release_type: bool,
    use_first_release_year: bool,
    use_record_label: bool,
    use_catalog_number: bool,
    expected: bool,
) -> None:
    actual = _require_mbid_resolution(
        use_release_type=use_release_type,
        use_first_release_year=use_first_release_year,
        use_record_label=use_record_label,
        use_catalog_number=use_catalog_number,
    )
    assert actual == expected, f"Expected {expected}, but got {actual}"


@pytest.mark.parametrize(
    "use_release_type, use_first_release_year, use_record_label, use_catalog_number, expected",
    [
        (False, False, False, False, set()),
        (False, False, False, True, {RED_PARAM_CATALOG_NUMBER}),
        (False, False, True, False, {RED_PARAM_RECORD_LABEL}),
        (False, True, False, False, {RED_PARAM_RELEASE_YEAR}),
        (True, False, False, False, {RED_PARAM_RELEASE_TYPE}),
        (True, False, False, True, {RED_PARAM_RELEASE_TYPE, RED_PARAM_CATALOG_NUMBER}),
        (True, False, True, False, {RED_PARAM_RELEASE_TYPE, RED_PARAM_RECORD_LABEL}),
        (True, True, False, False, {RED_PARAM_RELEASE_TYPE, RED_PARAM_RELEASE_YEAR}),
        (True, True, False, True, {RED_PARAM_RELEASE_TYPE, RED_PARAM_RELEASE_YEAR, RED_PARAM_CATALOG_NUMBER}),
        (True, True, True, False, {RED_PARAM_RELEASE_TYPE, RED_PARAM_RELEASE_YEAR, RED_PARAM_RECORD_LABEL}),
        (
            True,
            True,
            True,
            True,
            {RED_PARAM_RELEASE_TYPE, RED_PARAM_RELEASE_YEAR, RED_PARAM_RECORD_LABEL, RED_PARAM_CATALOG_NUMBER},
        ),
    ],
)
def test_required_search_kwargs(
    use_release_type: bool,
    use_first_release_year: bool,
    use_record_label: bool,
    use_catalog_number: bool,
    expected: set[str],
) -> None:
    actual = _required_search_kwargs(
        use_release_type=use_release_type,
        use_first_release_year=use_first_release_year,
        use_record_label=use_record_label,
        use_catalog_number=use_catalog_number,
    )
    assert actual == expected


@pytest.mark.parametrize(
    "mock_search_kwargs, required_kwargs, expected",
    [
        ({}, set(), True),
        ({RED_PARAM_RELEASE_TYPE: "track"}, set(), True),
        ({}, {RED_PARAM_RELEASE_TYPE}, False),
        ({RED_PARAM_RELEASE_TYPE: "track"}, {RED_PARAM_RELEASE_TYPE}, True),
        ({RED_PARAM_RELEASE_TYPE: "track"}, {RED_PARAM_RECORD_LABEL}, False),
        ({RED_PARAM_RELEASE_TYPE: "track"}, {RED_PARAM_RELEASE_TYPE, RED_PARAM_RECORD_LABEL}, False),
        (
            {RED_PARAM_RELEASE_TYPE: "track", RED_PARAM_RECORD_LABEL: "LabelX"},
            {RED_PARAM_RELEASE_TYPE, RED_PARAM_RECORD_LABEL},
            True,
        ),
    ],
)
def test_search_kwargs_has_all_required_fields(
    mock_search_kwargs: dict[str, Any], required_kwargs: set[str], expected: bool
) -> None:
    test_si = SearchItem(
        initial_info=LFMRec("artist", "Title", rt.ALBUM, rc.SIMILAR_ARTIST), search_kwargs=mock_search_kwargs
    )
    actual = test_si.search_kwargs_has_all_required_fields(required_kwargs=required_kwargs)
    assert actual == expected


def test_generate_summary_stats(tmp_path: pytest.FixtureRequest, valid_app_settings: AppSettings) -> None:
    mock_skipped_rows = [["fake"], ["also fake"]]
    mocked_failed_snatch_rows = [["a"], ["b c"], ["d"]]
    mocked_snatch_rows = [["snatch1"], ["snatch2", "snatch3"]]
    mocked_output_summary_dir_path = "/some/fake/path"
    with patch(
        "plastered.release_search.search_helpers.print_and_save_all_searcher_stats"
    ) as mock_print_and_save_all_searcher_stats_fn:
        search_state = SearchState(app_settings=valid_app_settings)
        search_state._skipped_snatch_summary_rows = mock_skipped_rows
        search_state._failed_snatches_summary_rows = mocked_failed_snatch_rows
        search_state._snatch_summary_rows = mocked_snatch_rows
        search_state._output_summary_dir_path = mocked_output_summary_dir_path

        search_state.generate_summary_stats()
        mock_print_and_save_all_searcher_stats_fn.assert_called_once_with(
            skipped_rows=mock_skipped_rows,
            failed_snatch_rows=mocked_failed_snatch_rows,
            snatch_summary_rows=mocked_snatch_rows,
            output_summary_dir_path=mocked_output_summary_dir_path,
        )


@pytest.mark.parametrize(
    "rec_type, info_field_present, expected",
    [(rt.ALBUM, False, None), (rt.TRACK, False, None), (rt.ALBUM, True, "mock-mbid"), (rt.TRACK, True, "mock-mbid")],
)
def test_search_item_get_matched_mbid(rec_type: rt, info_field_present: bool, expected: str | None) -> None:
    mock_mbid = "mock-mbid"
    si = SearchItem(initial_info=LFMRec("a", "e", rec_type, rc.SIMILAR_ARTIST))
    if info_field_present:
        if rec_type == rt.ALBUM:
            si.lfm_album_info = LFMAlbumInfo("art", "album", "", mock_mbid)
        else:
            si.lfm_track_info = LFMTrackInfo("art", "track", "", "", mock_mbid)
    actual = si.get_matched_mbid()
    assert actual == expected


@pytest.mark.parametrize(
    "mock_rec_type, mock_lfmti, expected_get_human_readable_entity_str_call_cnt, expected_result",
    [
        pytest.param(rt.ALBUM, None, 1, "Title", id="album rec"),
        pytest.param(rt.TRACK, None, 0, "None", id="track-no-lfmti"),
        pytest.param(
            rt.TRACK,
            LFMTrackInfo(artist="a", track_name="t", release_name="Title", lfm_url="fake", release_mbid="abc"),
            0,
            "Title",
            id="track-with-lfmti",
        ),
    ],
)
def test_search_item_release_name(
    mock_rec_type: rt,
    mock_lfmti: LFMTrackInfo | None,
    expected_get_human_readable_entity_str_call_cnt: int,
    expected_result: str,
) -> None:
    with patch.object(
        LFMRec, "get_human_readable_entity_str", return_value=expected_result
    ) as mock_lfm_rec_get_human_readable_track_str_method:
        si = SearchItem(
            initial_info=LFMRec("artist", "Title", mock_rec_type, rc.SIMILAR_ARTIST), lfm_track_info=mock_lfmti
        )
        actual = si.release_name
        assert actual == expected_result
        assert (
            len(mock_lfm_rec_get_human_readable_track_str_method.mock_calls)
            == expected_get_human_readable_entity_str_call_cnt
        )


def test_search_item_set_snatch_skipped_fields() -> None:
    si = SearchItem(initial_info=LFMRec("artist", "Title", rt.ALBUM, rc.SIMILAR_ARTIST))
    assert si.snatch_skip_reason is None
    assert si.search_result.skip_reason is None
    assert si.search_result.final_state is None
    si.set_snatch_skipped_fields(reason=sr.ALREADY_SNATCHED)
    assert si.snatch_skip_reason == sr.ALREADY_SNATCHED
    assert si.search_result.skip_reason == sr.ALREADY_SNATCHED
    assert si.search_result.final_state == FinalState.SKIPPED
