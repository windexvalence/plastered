from copy import deepcopy
import os
from pathlib import Path
import re
from copy import deepcopy
from typing import Any
from unittest.mock import ANY, MagicMock, Mock, call, patch

import pytest
from pytest_httpx import HTTPXMock

from plastered.config.app_settings import AppSettings, get_app_settings
from plastered.models.lfm_models import LFMAlbumInfo
from plastered.models.manual_search_models import ManualSearch
from plastered.models.search_item import SearchItem
from plastered.release_search.release_searcher import ReleaseSearcher, SearchState
from plastered.release_search.search_helpers import SearchState
from plastered.models.lfm_models import LFMRec
from plastered.models.types import EntityType as et, RecContext as rc
from plastered.run_cache.run_cache import RunCache
from plastered.utils.exceptions import RedClientSnatchException, ReleaseSearcherException
from plastered.utils.httpx_utils.lfm_client import LFMAPIClient
from plastered.utils.httpx_utils.musicbrainz_client import MusicBrainzAPIClient
from plastered.utils.httpx_utils.red_snatch_client import RedSnatchAPIClient
from plastered.models.lfm_models import LFMTrackInfo
from plastered.utils.log_utils import NestedProgress
from plastered.models.musicbrainz_models import MBRelease
from plastered.models.types import EncodingEnum as ee
from plastered.models.types import FormatEnum as fe
from plastered.models.types import MediaEnum as me
from plastered.models.red_models import RedFormat as rf
from plastered.models.red_models import RedUserDetails, TorrentMatch
from plastered.models.red_models import TorrentEntry as te


@pytest.fixture(scope="session")
def mock_lfmai() -> LFMAlbumInfo:
    return LFMAlbumInfo(artist="Foo", release_mbid="1234", album_name="Bar", lfm_url="https://blah.com")


@pytest.fixture(scope="function")
def mock_lfm_track_info() -> LFMTrackInfo:
    return LFMTrackInfo("Some Artist", "Track Title", "Source Album", "https://fake-url", "69-420")


@pytest.fixture(scope="function")
def initial_search_state(valid_app_settings: AppSettings) -> SearchState:
    return SearchState(app_settings=valid_app_settings)


@pytest.fixture(scope="session")
def mock_mbr() -> MBRelease:
    return MBRelease(
        mbid="1234",
        title="Bar",
        artist="Foo",
        primary_type="Album",
        release_date="2017-05-19",
        first_release_year=2016,
        label="Get On Down",
        catalog_number="58010",
        release_group_mbid="b38e21f6-8f76-3f87-a021-e91afad9e7e5",
    )


@pytest.fixture(scope="function", autouse=True)
def mock_best_te() -> te:
    return te(
        torrent_id=69420,
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


@pytest.mark.override_global_httpx_mock
def test_resolve_lfm_album_info(
    httpx_mock: HTTPXMock, mock_lfm_album_info_json: dict[str, Any], valid_app_settings: AppSettings
) -> None:
    httpx_mock.add_response(
        url="https://ws.audioscrobbler.com/2.0/?method=album.getinfo&api_key=5678alsonotarealapikey&artist=Some+Artist&album=Their+Album&format=json",
        headers={"Accept": "application/json"},
        json=mock_lfm_album_info_json,
    )
    with ReleaseSearcher(app_settings=valid_app_settings) as release_searcher:
        test_si = SearchItem(
            initial_info=LFMRec(
                lfm_artist_str="Some+Artist",
                lfm_entity_str="Their+Album",
                recommendation_type=et.ALBUM,
                rec_context=rc.IN_LIBRARY,
            )
        )
        release_searcher._resolve_lfm_album_info(si=test_si)


@pytest.mark.parametrize(
    "test_lfm_rec, mock_lfm_json_fixture, mb_resolved_origin_release_fields, expected_lfmti",
    [
        (
            LFMRec(
                lfm_artist_str="Dr.+Octagon",
                lfm_entity_str="No+Awareness",
                recommendation_type=et.TRACK,
                rec_context=rc.IN_LIBRARY,
            ),
            "mock_full_lfm_track_info_json",
            None,
            LFMTrackInfo(
                artist="Dr. Octagon",
                track_name="No Awareness",
                release_name="Dr. Octagonecologyst",
                lfm_url="https://www.last.fm/music/Dr.+Octagon/_/No+Awareness",
                release_mbid="cddbf21f-9cd8-4665-a015-3cdc50cdcc72",
            ),
        ),
        (
            LFMRec(
                lfm_artist_str="The+Tuss",
                lfm_entity_str="rushup+i+bank+12+M",
                recommendation_type=et.TRACK,
                rec_context=rc.IN_LIBRARY,
            ),
            "mock_no_album_lfm_track_info_json",
            {"origin_release_mbid": "3b08749b-b63e-46d3-b693-e0736faf046f", "origin_release_name": "Rushup Edge"},
            LFMTrackInfo(
                artist="The Tuss",
                track_name="rushup i bank 12 M",
                release_name="Rushup Edge",
                lfm_url="https://www.last.fm/music/The+Tuss/_/rushup+i+bank+12+M",
                release_mbid="3b08749b-b63e-46d3-b693-e0736faf046f",
            ),
        ),
        (
            LFMRec(
                lfm_artist_str="The+Tuss",
                lfm_entity_str="rushup+i+bank+12+M",
                recommendation_type=et.TRACK,
                rec_context=rc.IN_LIBRARY,
            ),
            "mock_no_album_lfm_track_info_json",
            None,
            None,
        ),
    ],
)
def test_resolve_lfm_track_info(
    request: pytest.FixtureRequest,
    valid_app_settings: AppSettings,
    test_lfm_rec: SearchItem,
    mock_lfm_json_fixture: str,
    mb_resolved_origin_release_fields: dict[str, str | None] | None,
    expected_lfmti: LFMTrackInfo | None,
) -> None:
    input_si = SearchItem(initial_info=test_lfm_rec)
    expected_si = SearchItem(initial_info=test_lfm_rec, lfm_track_info=expected_lfmti)
    mock_lfm_response = request.getfixturevalue(mock_lfm_json_fixture)["track"]
    with patch.object(LFMAPIClient, "request_api") as mock_lfm_request_api:
        mock_lfm_request_api.return_value = mock_lfm_response
        with patch.object(
            MusicBrainzAPIClient, "request_release_details_for_track"
        ) as mock_request_release_details_for_track:
            mock_request_release_details_for_track.return_value = mb_resolved_origin_release_fields
            with ReleaseSearcher(app_settings=valid_app_settings) as release_searcher:
                actual = release_searcher._resolve_lfm_track_info(si=input_si)
                mock_lfm_request_api.assert_called_once_with(
                    method="track.getinfo",
                    params=f"artist={input_si.initial_info.encoded_artist_str}&track={input_si.initial_info.encoded_entity_str}",
                )
                if "album" in mock_lfm_response:
                    mock_request_release_details_for_track.assert_not_called()
                else:
                    mock_request_release_details_for_track.assert_called_once()
                assert actual == expected_si, f"Expected {expected_si}, but got {actual}"


@pytest.mark.parametrize("lfm_api_response", [None, {"no-artist-key": "should-error"}])
def test_resolve_lfm_track_info_bad_json(
    valid_app_settings: AppSettings, lfm_api_response: dict[str, Any] | None
) -> None:
    rec = LFMRec("Fake+Artist", "Fake+Song", et.TRACK, rc.IN_LIBRARY)
    with patch.object(LFMAPIClient, "request_api") as mock_lfm_request_api:
        mock_lfm_request_api.return_value = lfm_api_response
        with patch.object(MusicBrainzAPIClient, "request_release_details_for_track") as mock_mb_request_method:
            mock_mb_request_method.return_value = {
                "origin_release_mbid": "69430-08749b-b",
                "origin_release_name": "Some Release",
            }
            with ReleaseSearcher(app_settings=valid_app_settings) as release_searcher:
                actual = release_searcher._resolve_lfm_track_info(si=SearchItem(initial_info=rec))
                assert actual is not None
                mock_mb_request_method.assert_called_once_with(
                    human_readable_track_name=rec.get_human_readable_track_str(),
                    artist_mbid=None,
                    human_readable_artist_name=rec.get_human_readable_artist_str(),
                )


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize(
    "test_si, mock_matched_mbid",
    [
        pytest.param(
            SearchItem(initial_info=LFMRec("artist", "ent", et.ALBUM, rc.IN_LIBRARY)), None, id="album-no-mbid"
        ),
        pytest.param(
            SearchItem(initial_info=LFMRec("artist", "ent", et.ALBUM, rc.IN_LIBRARY)),
            "d211379d-3203-47ed-a0c5-e564815bb45a",
            id="album-has-mbid",
        ),
        pytest.param(
            SearchItem(initial_info=LFMRec("artist", "ent", et.TRACK, rc.IN_LIBRARY)), None, id="track-no-mbid"
        ),
        pytest.param(
            SearchItem(initial_info=LFMRec("artist", "ent", et.TRACK, rc.IN_LIBRARY)),
            "d211379d-3203-47ed-a0c5-e564815bb45a",
            id="track-has-mbid",
        ),
    ],
)
def test_attempt_resolve_mb_release(
    httpx_mock: HTTPXMock,
    valid_app_settings: AppSettings,
    mock_musicbrainz_release_json: dict[str, Any],
    expected_mb_release: MBRelease,
    test_si: SearchItem,
    mock_matched_mbid: str | None,
) -> None:
    expected = deepcopy(test_si)
    if mock_matched_mbid:
        expected.set_mb_release(expected_mb_release)
    httpx_mock.add_response(
        url=f"https://musicbrainz.org/ws/2/release/{mock_matched_mbid}?inc=artist-credits+media+labels+release-groups",
        headers={"Accept": "application/json"},
        json=mock_musicbrainz_release_json,
    )
    with patch.object(SearchItem, "get_matched_mbid", return_value=mock_matched_mbid) as mock_get_matched_mbid_fn:
        with ReleaseSearcher(app_settings=valid_app_settings) as release_searcher:
            actual = release_searcher._attempt_resolve_mb_release(si=test_si)
            mock_get_matched_mbid_fn.assert_called_once()
            assert actual == expected


def test_gather_red_user_details(global_httpx_mock: HTTPXMock, valid_app_settings: AppSettings) -> None:
    expected_red_user_id = valid_app_settings.red.red_user_id
    expected_snatch_count = 216
    with patch("plastered.utils.httpx_utils.base_client.precise_delay") as mock_precise_delay:
        mock_precise_delay.return_value = None
        with ReleaseSearcher(app_settings=valid_app_settings) as release_searcher:
            assert release_searcher._search_state._red_user_details is None, (
                "Expected ReleaseSearcher's red user details to initially be None"
            )
            release_searcher._gather_red_user_details()
            assert release_searcher._search_state._red_user_details is not None
            red_user_details_user_id = release_searcher._search_state._red_user_details.user_id
            assert red_user_details_user_id == expected_red_user_id
            actual_snatch_count = release_searcher._search_state._red_user_details.snatched_count
            assert actual_snatch_count == expected_snatch_count


def test_search_empty_list(valid_app_settings: AppSettings) -> None:
    with patch("plastered.release_search.release_searcher._LOGGER") as mock_logger:
        mock_logger.warning.return_value = None
        with patch.object(ReleaseSearcher, "_search_for_release_te") as mock_search_for_release_te_fn:
            with ReleaseSearcher(app_settings=valid_app_settings) as release_searcher:
                release_searcher._search(search_items=[])
                mock_logger.warning.assert_called_once()
                mock_search_for_release_te_fn.assert_not_called()


@pytest.mark.parametrize(
    "search_items",
    [
        [
            SearchItem(initial_info=LFMRec("", "", et.ALBUM, rc.IN_LIBRARY)),
            SearchItem(initial_info=LFMRec("", "", et.TRACK, rc.IN_LIBRARY)),
        ],
        [
            SearchItem(initial_info=LFMRec("", "", et.TRACK, rc.IN_LIBRARY)),
            SearchItem(initial_info=LFMRec("", "", et.ALBUM, rc.IN_LIBRARY)),
        ],
        [
            SearchItem(initial_info=LFMRec("", "", et.ALBUM, rc.IN_LIBRARY)),
            SearchItem(initial_info=LFMRec("", "", et.ALBUM, rc.IN_LIBRARY)),
            SearchItem(initial_info=LFMRec("", "", et.TRACK, rc.IN_LIBRARY)),
            SearchItem(initial_info=LFMRec("", "", et.ALBUM, rc.IN_LIBRARY)),
        ],
    ],
)
def test_search_should_raise(valid_app_settings: AppSettings, search_items: list[SearchItem]) -> None:
    with pytest.raises(ReleaseSearcherException, match=re.escape("All search items must be of same entity_type.")):
        with ReleaseSearcher(app_settings=valid_app_settings) as release_searcher:
            release_searcher._search(search_items=search_items)


@pytest.mark.parametrize(
    "search_items, ",
    [
        [SearchItem(initial_info=LFMRec("a", "b", et.TRACK, rc.IN_LIBRARY))],
        [SearchItem(initial_info=LFMRec("c", "d", et.ALBUM, rc.IN_LIBRARY))],
        [
            SearchItem(initial_info=LFMRec("e", "f", et.ALBUM, rc.IN_LIBRARY)),
            SearchItem(initial_info=LFMRec("g", "h", et.ALBUM, rc.IN_LIBRARY)),
        ],
        [
            SearchItem(initial_info=LFMRec("i", "j", et.TRACK, rc.IN_LIBRARY)),
            SearchItem(initial_info=LFMRec("k", "l", et.TRACK, rc.IN_LIBRARY)),
            SearchItem(initial_info=LFMRec("m", "n", et.TRACK, rc.IN_LIBRARY)),
        ],
    ],
)
def test_search(valid_app_settings: AppSettings, mock_best_te: te, search_items: list[SearchItem]) -> None:
    # Shorthand hack to just mock the last elem as being viable to add to pending snatch list
    search_items[-1].torrent_entry = mock_best_te
    expected_search_for_release_te_call_count = len(search_items)
    expected_search_for_release_te_calls = [call(si=test_si, rich_progress=ANY) for test_si in search_items]
    mock_nested_progress = MagicMock()

    def _mock_search_for_release_te_side_effect(*args, **kwargs) -> SearchItem:
        si_: SearchItem = kwargs.get("si")
        return si_

    def _mock_nested_progress_track(*args, **kwargs) -> list[SearchItem]:
        search_items_: list[SearchItem] = args[0]
        return search_items_

    with (
        patch.object(
            ReleaseSearcher, "_search_for_release_te", side_effect=_mock_search_for_release_te_side_effect
        ) as mock_search_for_release_te_fn,
        patch.object(SearchState, "add_search_item_to_snatch") as mock_search_state_add_to_snatch_fn,
        patch.object(NestedProgress, "__enter__", return_value=mock_nested_progress) as mock_nested_progress_enter_fn,
    ):
        mock_nested_progress.track.side_effect = _mock_nested_progress_track
        with ReleaseSearcher(app_settings=valid_app_settings) as release_searcher:
            release_searcher._search(search_items=search_items)
            assert len(mock_search_for_release_te_fn.mock_calls) == expected_search_for_release_te_call_count
            mock_search_for_release_te_fn.assert_has_calls(expected_search_for_release_te_calls)
            mock_search_state_add_to_snatch_fn.assert_called_once_with(si=search_items[-1])


@pytest.mark.parametrize(
    "mock_response_fixture_names, mock_preference_ordering, expected_torrent_entry",
    [
        (  # Test case 1: empty browse results for first/only preference
            ["mock_red_browse_empty_response"],
            [rf(format=fe.FLAC, encoding=ee.TWO_FOUR_BIT_LOSSLESS, media=me.SACD)],
            None,
        ),
        (  # Test case 2: non-empty browse results for first preference
            ["mock_red_browse_non_empty_response"],
            [rf(format=fe.FLAC, encoding=ee.TWO_FOUR_BIT_LOSSLESS, media=me.WEB)],
            te(
                torrent_id=69420,
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
            ),
        ),
        (  # Test case 3: empty browse results for first pref, and non-empty browse results for 2nd preference
            ["mock_red_browse_empty_response", "mock_red_browse_non_empty_response"],
            [
                rf(format=fe.FLAC, encoding=ee.TWO_FOUR_BIT_LOSSLESS, media=me.SACD),
                rf(format=fe.FLAC, encoding=ee.TWO_FOUR_BIT_LOSSLESS, media=me.WEB),
            ],
            te(
                torrent_id=69420,
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
            ),
        ),
    ],
)
def test_search_red_release_by_preferences(
    request: pytest.FixtureRequest,
    valid_app_settings: AppSettings,
    mock_response_fixture_names: list[str],
    mock_preference_ordering: list[rf],
    expected_torrent_entry: te | None,
) -> None:
    expected_torrent_match = TorrentMatch(torrent_entry=expected_torrent_entry, above_max_size_found=False)
    mock_progress = MagicMock(spec=NestedProgress)
    with ReleaseSearcher(app_settings=valid_app_settings) as release_searcher:
        release_searcher._search_state._red_format_preferences = mock_preference_ordering
        release_searcher._red_client.request_api = Mock(
            name="request_api",
            side_effect=[
                request.getfixturevalue(fixture_name)["response"] for fixture_name in mock_response_fixture_names
            ],
        )
        actual_torrent_match = release_searcher._search_red_release_by_preferences(
            si=SearchItem(initial_info=LFMRec("Fake+Artist", "Fake+Release", et.ALBUM, rc.IN_LIBRARY)),
            rich_progress=mock_progress,
        )
        assert actual_torrent_match == expected_torrent_match


def test_search_red_release_by_preferences_above_max_size_found(
    request: pytest.FixtureRequest, valid_app_settings: AppSettings
) -> None:
    mock_preference_ordering = [
        rf(format=fe.FLAC, encoding=ee.TWO_FOUR_BIT_LOSSLESS, media=me.SACD),
        rf(format=fe.FLAC, encoding=ee.TWO_FOUR_BIT_LOSSLESS, media=me.WEB),
    ]
    # Test case 3: empty browse results for first pref, and non-empty browse results for 2nd preference
    mock_response_fixture_names = ["mock_red_browse_empty_response", "mock_red_browse_non_empty_response"]
    expected_torrent_match = TorrentMatch(torrent_entry=None, above_max_size_found=True)
    test_si = SearchItem(LFMRec("Fake+Artist", "Fake+Release", et.ALBUM, rc.IN_LIBRARY))
    mock_progress = MagicMock(spec=NestedProgress)
    with ReleaseSearcher(app_settings=valid_app_settings) as release_searcher:
        release_searcher._search_state._max_size_gb = 0.00001
        release_searcher._search_state._red_format_preferences = mock_preference_ordering
        release_searcher._red_client.request_api = Mock(
            name="request_api",
            side_effect=[
                request.getfixturevalue(fixture_name)["response"] for fixture_name in mock_response_fixture_names
            ],
        )
        actual_torrent_match = release_searcher._search_red_release_by_preferences(
            si=test_si, rich_progress=mock_progress
        )
        assert actual_torrent_match == expected_torrent_match


def test_search_red_release_by_preferences_browse_exception_raised(valid_app_settings: AppSettings) -> None:
    expected = TorrentMatch(torrent_entry=None, above_max_size_found=False)

    def _raise_excp(*args, **kwargs) -> None:
        raise Exception("Fake exception")

    test_si = SearchItem(LFMRec("Fake+Artist", "Fake+Release", et.ALBUM, rc.IN_LIBRARY))
    mock_progress = MagicMock(spec=NestedProgress)
    with (
        patch("plastered.release_search.release_searcher._LOGGER") as mock_logger,
        ReleaseSearcher(app_settings=valid_app_settings) as release_searcher,
    ):
        mock_logger.error.return_value = None
        release_searcher._search_state._red_format_preferences = [
            rf(format=fe.FLAC, encoding=ee.TWO_FOUR_BIT_LOSSLESS, media=me.SACD)
        ]
        release_searcher._red_client.request_api = Mock(name="request_api", side_effect=_raise_excp)
        actual = release_searcher._search_red_release_by_preferences(si=test_si, rich_progress=mock_progress)
        assert actual == expected
        mock_logger.error.assert_called_once()


@pytest.mark.parametrize(
    "pre_mbid_resolution_filter_res, require_mbid_resolution, post_mbid_resolution_filter_res, post_red_search_filer_res",
    [(False, False, False, False), (True, False, False, False), (True, True, False, False), (True, True, True, False)],
)
def test_search_for_release_te_none(
    valid_app_settings: AppSettings,
    mock_lfmai: LFMAlbumInfo,
    mock_mbr: MBRelease,
    pre_mbid_resolution_filter_res: bool,
    require_mbid_resolution: bool,
    post_mbid_resolution_filter_res: bool,
    post_red_search_filer_res: bool,
) -> None:
    """Validates that the conditions where _search_for_release_te should return non-None do so."""
    expect_resolve_calls = pre_mbid_resolution_filter_res and require_mbid_resolution
    expect_search_red_call = expect_resolve_calls and post_mbid_resolution_filter_res

    def _mock_attempt_resolve_mb_release_side_effect(*args, **kwargs) -> SearchItem:
        _si: SearchItem = kwargs.get("si")
        _si.set_mb_release(mock_mbr)
        return _si

    mock_progress = MagicMock(spec=NestedProgress)
    with (
        patch.object(
            SearchState, "pre_mbid_resolution_filter", return_value=pre_mbid_resolution_filter_res
        ) as mock_ss_pre_mbid_filter,
        patch.object(ReleaseSearcher, "_resolve_lfm_album_info", return_value=mock_lfmai) as mock_resolve_lfmai,
        patch.object(
            ReleaseSearcher, "_attempt_resolve_mb_release", side_effect=_mock_attempt_resolve_mb_release_side_effect
        ) as mock_resolve_mbr,
        patch.object(
            SearchState, "post_mbid_resolution_filter", return_value=post_mbid_resolution_filter_res
        ) as mock_post_mbid_filter,
        patch.object(
            ReleaseSearcher,
            "_search_red_release_by_preferences",
            return_value=TorrentMatch(torrent_entry=None, above_max_size_found=False),
        ) as mock_search_red_by_prefs,
        patch.object(
            SearchState, "post_red_search_filter", return_value=post_red_search_filer_res
        ) as mock_ss_post_red_filter,
    ):
        with ReleaseSearcher(app_settings=valid_app_settings) as release_searcher:
            release_searcher._search_state._require_mbid_resolution = require_mbid_resolution
            si = SearchItem(LFMRec("a", "aa", et.ALBUM, rc.SIMILAR_ARTIST))
            actual = release_searcher._search_for_release_te(si=si, rich_progress=mock_progress)
            assert actual is None
            mock_ss_pre_mbid_filter.assert_called_once()
            if expect_resolve_calls:
                mock_resolve_lfmai.assert_called_once()
                mock_resolve_mbr.assert_called_once()
                mock_post_mbid_filter.assert_called_once()
                if expect_search_red_call:
                    mock_search_red_by_prefs.assert_called_once()
                    mock_ss_post_red_filter.assert_called_once()


@pytest.mark.parametrize("require_mbid_resolution", [False, True])
def test_search_for_release_te(
    valid_app_settings: AppSettings,
    mock_lfmai: LFMAlbumInfo,
    mock_mbr: MBRelease,
    mock_best_te: te,
    require_mbid_resolution: bool,
) -> None:
    """Validates that the conditions where _search_for_release_te should return non-None do so."""

    def _mock_attempt_resolve_mb_release_side_effect(*args, **kwargs) -> SearchItem:
        _si: SearchItem = kwargs.get("si")
        _si.set_mb_release(mock_mbr)
        return _si

    # TODO: consolidate mock_progress instances as fixture
    mock_progress = MagicMock(spec=NestedProgress)
    with (
        patch.object(SearchState, "pre_mbid_resolution_filter", return_value=True) as mock_ss_pre_filter,
        patch.object(SearchState, "post_red_search_filter", return_value=True) as mock_ss_post_filter,
        patch.object(ReleaseSearcher, "_resolve_lfm_album_info", return_value=mock_lfmai) as mock_resolve_lfmai,
        patch.object(
            ReleaseSearcher, "_attempt_resolve_mb_release", side_effect=_mock_attempt_resolve_mb_release_side_effect
        ) as mock_resolve_mbr,
        patch.object(
            ReleaseSearcher,
            "_search_red_release_by_preferences",
            return_value=TorrentMatch(torrent_entry=mock_best_te, above_max_size_found=False),
        ) as mocked_torrent_match,
    ):
        with ReleaseSearcher(app_settings=valid_app_settings) as release_searcher:
            release_searcher._search_state._require_mbid_resolution = require_mbid_resolution
            si = SearchItem(LFMRec("", "", et.ALBUM, rc.SIMILAR_ARTIST))
            actual = release_searcher._search_for_release_te(si=si, rich_progress=mock_progress)
            mock_ss_pre_filter.assert_called_once()
            mock_ss_post_filter.assert_called_once()
    assert actual is not None
    assert actual.torrent_entry is not None
    assert actual.torrent_entry == mock_best_te


@pytest.mark.parametrize(
    "mock_resolved_lfmti",
    [None, LFMTrackInfo("Some Artist", "Track Title", "Source Album", "https://fake-url", "69-420")],
)
def test_search_for_track_recs(valid_app_settings: AppSettings, mock_resolved_lfmti: LFMTrackInfo | None) -> None:
    test_si = SearchItem(initial_info=LFMRec("Some+Artist", "Track+Title", et.TRACK, rc.SIMILAR_ARTIST))
    mock_si_with_resolved_ti = deepcopy(test_si)
    mock_si_with_resolved_ti.lfm_track_info = mock_resolved_lfmti
    with patch.object(ReleaseSearcher, "_search") as mock_search_fn:
        with patch.object(ReleaseSearcher, "_resolve_lfm_track_info") as mock_resolve_lfm_track_info:
            mock_resolve_lfm_track_info.return_value = mock_si_with_resolved_ti
            mock_search_fn.return_value = None
            with ReleaseSearcher(app_settings=valid_app_settings) as release_searcher:
                release_searcher._search_for_track_recs(search_items=[test_si])
                mock_resolve_lfm_track_info.assert_called_once_with(si=test_si)
                if not mock_resolved_lfmti:
                    mock_search_fn.assert_called_once_with(search_items=[])
                else:
                    mock_search_fn.assert_called_once_with(search_items=[mock_si_with_resolved_ti])


def test_search_for_track_recs_empty_input(valid_app_settings: AppSettings) -> None:
    with patch.object(ReleaseSearcher, "_search") as mock_search_fn:
        with patch.object(ReleaseSearcher, "_resolve_lfm_track_info") as mock_resolve_lfm_track_info_fn:
            with ReleaseSearcher(app_settings=valid_app_settings) as release_searcher:
                release_searcher._search_for_track_recs(search_items=[])
                mock_resolve_lfm_track_info_fn.assert_not_called()
                mock_search_fn.assert_not_called()


@pytest.mark.parametrize(
    "rec_type_to_recs_list, expected_search_call_cnt",
    [
        ({}, 0),
        ({et.ALBUM: [LFMRec("Some+Artist", "Some+Album", et.ALBUM, rc.SIMILAR_ARTIST)]}, 1),
        ({et.TRACK: [LFMRec("Some+Artist", "Some+Track", et.TRACK, rc.IN_LIBRARY)]}, 1),
        (
            {
                et.ALBUM: [LFMRec("Some+Artist", "Some+Album", et.ALBUM, rc.SIMILAR_ARTIST)],
                et.TRACK: [LFMRec("Some+Artist", "Some+Track", et.TRACK, rc.IN_LIBRARY)],
            },
            2,
        ),
    ],
)
def test_search_for_recs(
    valid_app_settings: AppSettings, rec_type_to_recs_list: dict[et, list[LFMRec]], expected_search_call_cnt: int
) -> None:
    def _resolve_lfmti_side_effect(*args, **kwargs) -> SearchItem:
        input_si: SearchItem = kwargs["si"]
        resolved_search_item = deepcopy(input_si)
        resolved_search_item.lfm_track_info = LFMTrackInfo(
            artist=input_si.artist_name,
            track_name=input_si.track_name,
            release_mbid="foo",
            release_name="title",
            lfm_url=input_si.initial_info.lfm_entity_url,
        )
        return resolved_search_item

    with (
        patch.object(ReleaseSearcher, "_gather_red_user_details", return_value=None) as mock_gather_red_user_details,
        patch.object(
            ReleaseSearcher, "_resolve_lfm_track_info", side_effect=_resolve_lfmti_side_effect
        ) as mock_resolve_lfm_track_info,
        patch.object(ReleaseSearcher, "_search", return_value=None) as mock_search,
        patch.object(ReleaseSearcher, "_snatch_matches", return_value=None) as mock_snatch_matches,
    ):
        with ReleaseSearcher(app_settings=valid_app_settings) as release_searcher:
            release_searcher.search_for_recs(rec_type_to_recs_list=rec_type_to_recs_list)
            mock_gather_red_user_details.assert_called_once()
            actual_search_call_cnt = len(mock_search.mock_calls)
            assert actual_search_call_cnt == expected_search_call_cnt
            mock_snatch_matches.assert_called_once()


# TODO (later): re-enable this test case once the RedUserDetails initialization takes place in the __enter__ method for ReleaseSearcher.
# def test_search_for_album_recs_invalid_user_details(valid_app_config: AppConfig) -> None:
#     with pytest.raises(ReleaseSearcherException, match="self._red_user_details has not yet been populated"):
#         with ReleaseSearcher(app_config=valid_app_config) as release_searcher:
#             release_searcher._search(
#                 search_items=[SearchItem(lfm_rec=LFMRec("A", "B", et.ALBUM, rc.IN_LIBRARY))],
#             )


@pytest.mark.parametrize(
    "mock_enable_snatches, mock_tes_to_snatch, expected_out_filenames, expected_request_params",
    [
        (False, [], [], []),
        (True, [], [], []),
        (
            False,
            [
                te(
                    torrent_id=69420,
                    media="CD",
                    format="FLAC",
                    encoding="Lossless",
                    size=12345,
                    scene=False,
                    trumpable=False,
                    has_snatched=False,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    can_use_token=False,
                ),
                te(
                    torrent_id=666,
                    media="CD",
                    format="FLAC",
                    encoding="Lossless",
                    size=12345,
                    scene=False,
                    trumpable=False,
                    has_snatched=False,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    can_use_token=False,
                ),
            ],
            [],
            [],
        ),
        (
            True,
            [
                te(
                    torrent_id=69420,
                    media="CD",
                    format="FLAC",
                    encoding="Lossless",
                    size=12345,
                    scene=False,
                    trumpable=False,
                    has_snatched=False,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    can_use_token=False,
                ),
                te(
                    torrent_id=666,
                    media="CD",
                    format="FLAC",
                    encoding="Lossless",
                    size=12345,
                    scene=False,
                    trumpable=False,
                    has_snatched=False,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    can_use_token=False,
                ),
            ],
            ["69420.torrent", "666.torrent"],
            ["69420", "666"],
        ),
    ],
)
def test_snatch_matches(
    tmp_path: pytest.FixtureRequest,
    valid_config_raw_data: dict[str, Any],
    valid_config_filepath: str,
    mock_red_user_details_fn_scoped: RedUserDetails,
    mock_enable_snatches: bool,
    mock_tes_to_snatch: list[te],
    expected_out_filenames: list[str],
    expected_request_params: list[str],
) -> None:
    mocked_settings_data = deepcopy(valid_config_raw_data)
    for raw_k, raw_v in {"snatch_recs": mock_enable_snatches, "snatch_directory": tmp_path}.items():
        mocked_settings_data["red"]["snatches"][raw_k] = raw_v
    mocked_settings_data["src_yaml_filepath"] = Path(valid_config_filepath)
    mock_search_items_to_snatch = [
        SearchItem(torrent_entry=te, initial_info=LFMRec("", "", et.ALBUM, rc.IN_LIBRARY)) for te in mock_tes_to_snatch
    ]

    with patch("plastered.config.app_settings._get_settings_data", return_value=mocked_settings_data):
        app_settings = get_app_settings(src_yaml_filepath=Path(valid_config_filepath))
        with patch.object(RedSnatchAPIClient, "snatch") as mock_red_client_snatch:
            mock_red_client_snatch.return_value = bytes("fakedata", encoding="utf-8")
            expected_output_filepaths = [os.path.join(tmp_path, filename) for filename in expected_out_filenames]
            with ReleaseSearcher(app_settings=app_settings) as release_searcher:
                release_searcher._search_state._search_items_to_snatch = mock_search_items_to_snatch
                release_searcher._search_state.set_red_user_details(mock_red_user_details_fn_scoped)
                release_searcher._snatch_matches()
                if not mock_enable_snatches:
                    mock_red_client_snatch.assert_not_called()
                    assert all([not tmp_filename.endswith(".torrent") for tmp_filename in os.listdir(tmp_path)])
                else:
                    mock_red_client_snatch.assert_has_calls(
                        [
                            call(tid=expected_request_param, can_use_token=False)
                            for expected_request_param in expected_request_params
                        ]
                    )
                    assert all([os.path.exists(out_filepath) for out_filepath in expected_output_filepaths])


@pytest.mark.parametrize(
    "exception_type, mock_file_exists",
    [(RedClientSnatchException, False), (RedClientSnatchException, True), (OSError, False), (OSError, True)],
)
def test_snatch_exception_handling(
    tmp_path: pytest.FixtureRequest,
    valid_config_raw_data: dict[str, Any],
    valid_config_filepath: str,
    mock_best_te: te,
    mock_red_user_details_fn_scoped: RedUserDetails,
    exception_type: Exception,
    mock_file_exists: bool,
) -> None:
    mocked_settings_data = deepcopy(valid_config_raw_data)
    mocked_settings_data["red"]["snatches"]["snatch_directory"] = tmp_path
    mocked_settings_data["src_yaml_filepath"] = Path(valid_config_filepath)

    def _red_client_raise_exception_side_effect(*args, **kwargs) -> None:
        raise exception_type("Expected testing exception")

    with patch("plastered.config.app_settings._get_settings_data", return_value=mocked_settings_data):
        app_settings = get_app_settings(src_yaml_filepath=Path(valid_config_filepath))
        with patch.object(RedSnatchAPIClient, "snatch") as mock_red_client_snatch:
            mock_red_client_snatch.side_effect = _red_client_raise_exception_side_effect
            expected_out_filepath = os.path.join(tmp_path, "69420.torrent")
            with ReleaseSearcher(app_settings=app_settings) as release_searcher:
                release_searcher._search_state._search_items_to_snatch = [
                    SearchItem(torrent_entry=mock_best_te, initial_info=LFMRec("", "", et.ALBUM, rc.IN_LIBRARY))
                ]
                release_searcher._search_state.set_red_user_details(mock_red_user_details_fn_scoped)
                if mock_file_exists:
                    with open(expected_out_filepath, "wb") as tf:
                        tf.write(bytes("fakedata", encoding="utf-8"))
                release_searcher._snatch_matches()
                assert not os.path.exists(expected_out_filepath)
                expected_failed_snatch_rows = [[mock_best_te.get_permalink_url(), "", exception_type.__name__]]
                actual_failed_snatch_rows = release_searcher._search_state._failed_snatches_summary_rows
                assert actual_failed_snatch_rows == expected_failed_snatch_rows, (
                    f"expected {expected_failed_snatch_rows}, but got {actual_failed_snatch_rows}"
                )


def test_generate_summary_stats(tmp_path: pytest.FixtureRequest, valid_app_settings: AppSettings) -> None:
    with patch.object(SearchState, "generate_summary_stats") as mock_search_state_gen_stats_fn:
        with ReleaseSearcher(app_settings=valid_app_settings) as release_searcher:
            mock_output_summary_dir_path = os.path.join(tmp_path, "1969-12-31__10-10-59")
            release_searcher._search_state._output_summary_dir_path = mock_output_summary_dir_path
            mock_search_state_gen_stats_fn.return_value = None
            release_searcher.generate_summary_stats()
            mock_search_state_gen_stats_fn.assert_called_once()


@pytest.mark.parametrize(
    "entity_type, expected_search_calls, expected_track_search_calls", [(et.ALBUM, 1, 0), (et.TRACK, 0, 1)]
)
def test_manual_search(
    valid_app_settings: AppSettings, entity_type: et, expected_search_calls, expected_track_search_calls
) -> None:
    manual_query = ManualSearch(entity_type=entity_type, artist="foo", entity="bar")
    with (
        patch.object(ReleaseSearcher, "_search") as mock_search,
        patch.object(ReleaseSearcher, "_search_for_track_recs") as mock_track_search,
        patch.object(ReleaseSearcher, "_snatch_matches") as mock_snatch_matches,
        ReleaseSearcher(app_settings=valid_app_settings) as release_searcher,
    ):
        release_searcher._run_cache = MagicMock(spec=RunCache)
        release_searcher.manual_search(manual_search_instance=manual_query)
        assert len(mock_search.mock_calls) == expected_search_calls
        assert len(mock_track_search.mock_calls) == expected_track_search_calls
        release_searcher._run_cache.close.assert_called_once()
        mock_snatch_matches.assert_called_once_with(manual_run=True)
