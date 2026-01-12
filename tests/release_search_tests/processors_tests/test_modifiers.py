from collections.abc import Callable
from copy import deepcopy
from typing import Any, TypedDict
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from pytest_httpx import HTTPXMock

from plastered.config.app_settings import AppSettings
from plastered.db.db_models import SearchRecord, SkipReason
from plastered.models import (
    EncodingEnum,
    EntityType,
    FormatEnum,
    LFMAlbumInfo,
    LFMRec,
    LFMTrackInfo,
    MBRelease,
    MediaEnum,
    RecContext,
    RedFormat,
    ReleaseEntry,
    SearchItem,
    TorrentEntry,
    TorrentMatch,
)
from plastered.release_search.processors.modifiers import (
    ResolveAlbumInfoModifier,
    ResolveTrackInfoModifier,
    AttachSearchIdModifier,
    AttemptResolveMBReleaseModifier,
    SearchRedReleaseByPrefsModifier,
)
from plastered.release_search.processors.bases import SearchItemModifier
from plastered.release_search.search_helpers import SearchState
from plastered.utils.exceptions import LFMClientException, MusicBrainzClientException
from plastered.utils.httpx_utils.base_client import ThrottledAPIBaseClient
from plastered.utils.httpx_utils import LFMAPIClient, MusicBrainzAPIClient, RedAPIClient


class _MockProcKwargs(TypedDict):
    state: SearchState
    lfm: LFMAPIClient
    mb: MusicBrainzAPIClient
    red: RedAPIClient


@pytest.fixture(scope="function")
def mock_process_kwargs() -> _MockProcKwargs:
    return _MockProcKwargs(
        state=MagicMock(spec=SearchState),
        lfm=MagicMock(spec=LFMAPIClient),
        mb=MagicMock(spec=MusicBrainzAPIClient),
        red=MagicMock(spec=RedAPIClient),
    )


_MOCK_TE_KWARGS: dict[str, Any] = {
    "size": 69420,
    "scene": False,
    "trumpable": False,
    "has_snatched": False,
    "has_log": False,
    "log_score": 0,
    "has_cue": False,
    "can_use_token": False,
    "reported": None,
    "lossy_web": None,
    "lossy_master": None,
}


@pytest.mark.parametrize("entity_type", [et for et in EntityType])
@pytest.mark.parametrize(
    "filter_class",
    [
        ResolveAlbumInfoModifier,
        ResolveTrackInfoModifier,
        AttachSearchIdModifier,
        AttemptResolveMBReleaseModifier,
        SearchRedReleaseByPrefsModifier,
    ],
)
def test_modifier_process(
    make_album_search_item: pytest.FixtureRequest,
    make_track_search_item: pytest.FixtureRequest,
    entity_type: EntityType,
    filter_class: SearchItemModifier,
) -> None:
    if filter_class == ResolveTrackInfoModifier and entity_type == EntityType.ALBUM:
        pytest.skip(f"{ResolveTrackInfoModifier.__class__.__qualname__} not relevant for albums.")
    mock_si = (
        make_album_search_item(is_lfm_rec=True)
        if entity_type == EntityType.ALBUM
        else make_track_search_item(is_lfm_rec=True)
    )

    pass  # TODO: implement


@pytest.mark.parametrize("is_lfm_rec", [False, True])
def test_resolve_album_info_modifier(
    mock_lfmai: LFMAlbumInfo,
    make_album_search_item: pytest.FixtureRequest,
    mock_process_kwargs: _MockProcKwargs,
    is_lfm_rec: bool,
) -> None:
    mock_si = make_album_search_item(is_lfm_rec=is_lfm_rec)
    assert mock_si._lfm_track_info is None
    with patch.object(
        LFMAlbumInfo, "construct_from_api_response", return_value=mock_lfmai
    ) as mock_construct_from_api_response:
        actual = ResolveAlbumInfoModifier.process(si=mock_si, **mock_process_kwargs)
        assert actual is mock_si
        if is_lfm_rec:
            mock_construct_from_api_response.assert_called_once()
            assert actual._lfm_album_info is not None
        else:
            mock_construct_from_api_response.assert_not_called()
            assert actual._lfm_album_info is None


@pytest.mark.parametrize(
    "test_lfm_rec, mock_lfm_json_fixture, mb_resolved_origin_release_fields, expected_lfmti",
    [
        (
            LFMRec(
                lfm_artist_str="Dr.+Octagon",
                lfm_entity_str="No+Awareness",
                recommendation_type=EntityType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
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
                recommendation_type=EntityType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
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
                recommendation_type=EntityType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            "mock_no_album_lfm_track_info_json",
            None,
            None,
        ),
    ],
)
def test_resolve_track_info_modifier(
    request: pytest.FixtureRequest,
    mock_process_kwargs: _MockProcKwargs,
    test_lfm_rec: SearchItem,
    mock_lfm_json_fixture: str,
    mb_resolved_origin_release_fields: dict[str, str | None] | None,
    expected_lfmti: LFMTrackInfo | None,
) -> None:
    input_si = SearchItem(initial_info=test_lfm_rec)
    mock_lfm_response = request.getfixturevalue(mock_lfm_json_fixture)["track"]
    mock_process_kwargs["lfm"].get_track_info.return_value = mock_lfm_response
    mock_process_kwargs["mb"].request_release_details_for_track.return_value = mb_resolved_origin_release_fields
    actual = ResolveTrackInfoModifier.process(si=input_si, **mock_process_kwargs)
    mock_process_kwargs["lfm"].get_track_info.assert_called_once_with(si=input_si)
    if "album" in mock_lfm_response:
        mock_process_kwargs["mb"].request_release_details_for_track.assert_not_called()
    else:
        mock_process_kwargs["mb"].request_release_details_for_track.assert_called_once()

    assert actual._lfm_track_info == expected_lfmti, f"Expected {expected_lfmti}, but got {actual}"


@pytest.mark.parametrize("is_lfm_rec", [False, True])
@pytest.mark.parametrize(
    "mb_resolved_origin_release_fields",
    [{"origin_release_mbid": "3b08749b-b63e-46d3-b693-e0736faf046f", "origin_release_name": "Rushup Edge"}, None],
)
def test_resolve_track_info_modifier_lfm_client_exception(
    mock_process_kwargs: _MockProcKwargs,
    make_track_search_item: pytest.FixtureRequest,
    is_lfm_rec: bool,
    mb_resolved_origin_release_fields: dict[str, str | None] | None,
) -> None:
    def _lfm_client_side_effect(*args: Any, **kwargs: Any) -> None:
        raise LFMClientException("Intentionally raised exception")

    mock_process_kwargs["lfm"].get_track_info.side_effect = _lfm_client_side_effect
    mock_process_kwargs["mb"].request_release_details_for_track.return_value = mb_resolved_origin_release_fields
    mock_si = make_track_search_item(is_lfm_rec=is_lfm_rec)
    with patch.object(SearchItem, "set_lfm_track_info") as mock_set_lfm_track_info:
        actual = ResolveTrackInfoModifier.process(si=mock_si, **mock_process_kwargs)
        assert isinstance(actual, SearchItem)
        mock_process_kwargs["mb"].request_release_details_for_track.assert_called_once_with(
            si=mock_si, artist_mbid=None
        )
        if mb_resolved_origin_release_fields is not None:
            mock_set_lfm_track_info.assert_called_once()
        else:
            mock_set_lfm_track_info.assert_not_called


@pytest.mark.parametrize("is_lfm_rec", [False, True])
@pytest.mark.parametrize("entity_type", [et for et in EntityType])
def test_attach_search_id_modifier(
    mock_process_kwargs: _MockProcKwargs,
    make_album_search_item: pytest.FixtureRequest,
    make_track_search_item: pytest.FixtureRequest,
    is_lfm_rec: bool,
    entity_type: EntityType,
) -> None:
    si = (
        make_album_search_item(is_lfm_rec=is_lfm_rec)
        if entity_type == EntityType.ALBUM
        else make_track_search_item(is_lfm_rec=is_lfm_rec)
    )
    expected_search_id = 69
    assert si.search_id is None

    def _add_record_side_effect(model_inst: SearchRecord) -> None:
        model_inst.id = expected_search_id

    with patch(
        "plastered.release_search.processors.modifiers.add_record", side_effect=_add_record_side_effect
    ) as mock_add_record:
        actual = AttachSearchIdModifier.process(si=si, **mock_process_kwargs)
        assert actual is si
        if is_lfm_rec:
            mock_add_record.assert_called_once()
            assert si.search_id == expected_search_id
        else:
            mock_add_record.assert_not_called()


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize("is_lfm_rec", [False, True])
@pytest.mark.parametrize("entity_type", [et for et in EntityType])
@pytest.mark.parametrize("has_matched_mbid", [False, True])
def test_attempt_resolve_mb_release_modifier(
    mock_musicbrainz_release_json: dict[str, Any],
    mock_process_kwargs: _MockProcKwargs,
    make_album_search_item: pytest.FixtureRequest,
    make_track_search_item: pytest.FixtureRequest,
    is_lfm_rec: bool,
    entity_type: EntityType,
    has_matched_mbid: bool,
) -> None:
    mock_matched_mbid = "69-420" if has_matched_mbid else None
    si: SearchItem = (
        make_album_search_item(is_lfm_rec=is_lfm_rec)
        if entity_type == EntityType.ALBUM
        else make_track_search_item(is_lfm_rec=is_lfm_rec)
    )
    if entity_type == EntityType.TRACK:
        lfmti = LFMTrackInfo(
            artist=si.artist_name,
            track_name=si.track_name,
            release_name=si.release_name,
            lfm_url="abc",
            release_mbid=mock_matched_mbid,
        )
        si._lfm_track_info = lfmti
    else:
        lfmai = LFMAlbumInfo(
            artist=si.artist_name, album_name=si.release_name, lfm_url="abc", release_mbid=mock_matched_mbid
        )
        si._lfm_album_info = lfmai

    expected_mb_release = (
        MBRelease.construct_from_api(json_blob=mock_musicbrainz_release_json) if has_matched_mbid else None
    )
    mock_process_kwargs["mb"].request_release_details.return_value = mock_musicbrainz_release_json
    actual = AttemptResolveMBReleaseModifier.process(si=si, **mock_process_kwargs)
    assert actual is si
    assert actual._mb_release == expected_mb_release


@pytest.mark.parametrize("is_lfm_rec", [False, True])
@pytest.mark.parametrize("entity_type", [et for et in EntityType])
def test_attempt_resolve_mb_release_modifier_exception(
    mock_process_kwargs: _MockProcKwargs,
    make_album_search_item: pytest.FixtureRequest,
    make_track_search_item: pytest.FixtureRequest,
    is_lfm_rec: bool,
    entity_type: EntityType,
) -> None:
    mock_matched_mbid = "69-420"
    mock_si = (
        make_album_search_item(is_lfm_rec=is_lfm_rec)
        if entity_type == EntityType.ALBUM
        else make_track_search_item(is_lfm_rec=is_lfm_rec)
    )
    if entity_type == EntityType.TRACK:
        lfmti = LFMTrackInfo(
            artist=mock_si.artist_name,
            track_name=mock_si.track_name,
            release_name=mock_si.release_name,
            lfm_url="abc",
            release_mbid=mock_matched_mbid,
        )
        mock_si._lfm_track_info = lfmti
    else:
        lfmai = LFMAlbumInfo(
            artist=mock_si.artist_name, album_name=mock_si.release_name, lfm_url="abc", release_mbid=mock_matched_mbid
        )
        mock_si._lfm_album_info = lfmai

    def _mb_request_release_details_side_effect(*args: Any, **kwargs: Any) -> None:
        raise MusicBrainzClientException("Intentionally raised exception")

    mock_process_kwargs["mb"].request_release_details.side_effect = _mb_request_release_details_side_effect
    actual = AttemptResolveMBReleaseModifier.process(si=mock_si, **mock_process_kwargs)
    assert isinstance(actual, SearchItem)


@pytest.fixture(scope="function")
def mock_te_from_size_factory() -> Callable[[float], TorrentEntry]:
    def _mock_te_from_size(size: float) -> TorrentEntry:
        mock_te_kwargs = deepcopy(_MOCK_TE_KWARGS)
        del mock_te_kwargs["size"]
        return TorrentEntry(
            size=size, torrent_id=69420, media="WEB", format="FLAC", encoding="24bit Lossless", **mock_te_kwargs
        )

    return _mock_te_from_size


class TestSearchRedReleaseByPrefsModifier:
    @pytest.mark.parametrize("is_lfm_rec", [False, True])
    @pytest.mark.parametrize(
        "mock_response_fixture_names, mock_preference_ordering, expected_torrent_entry",
        [
            (  # Test case 1: empty browse results for first/only preference
                ["mock_red_browse_empty_response"],
                [RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.SACD)],
                None,
            ),
            (  # Test case 2: non-empty browse results for first preference
                ["mock_red_browse_non_empty_response"],
                [RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB)],
                TorrentEntry(
                    torrent_id=69420, media="WEB", format="FLAC", encoding="24bit Lossless", **_MOCK_TE_KWARGS
                ),
            ),
            (  # Test case 3: empty browse results for first pref, and non-empty browse results for 2nd preference
                ["mock_red_browse_empty_response", "mock_red_browse_non_empty_response"],
                [
                    RedFormat(
                        format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.SACD
                    ),
                    RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
                ],
                TorrentEntry(
                    torrent_id=69420, media="WEB", format="FLAC", encoding="24bit Lossless", **_MOCK_TE_KWARGS
                ),
            ),
        ],
    )
    def test_search_red_release_by_prefs_modifier(
        self,
        request: pytest.FixtureRequest,
        mock_process_kwargs: _MockProcKwargs,
        make_album_search_item: pytest.FixtureRequest,
        is_lfm_rec: bool,
        mock_response_fixture_names: list[str],
        mock_preference_ordering: list[RedFormat],
        expected_torrent_entry: TorrentEntry | None,
    ) -> None:
        type(mock_process_kwargs["state"]).red_format_preferences = PropertyMock(return_value=mock_preference_ordering)
        mock_process_kwargs["red"].browse.side_effect = [
            request.getfixturevalue(fixture_name)["response"] for fixture_name in mock_response_fixture_names
        ]
        mock_si = make_album_search_item(is_lfm_rec=is_lfm_rec)
        assert mock_si.torrent_entry is None
        with patch.object(
            SearchRedReleaseByPrefsModifier,
            "_torrent_match_from_browse_results",
            return_value=TorrentMatch(torrent_entry=expected_torrent_entry, above_max_size_found=False),
        ) as mock_tm_from_browse_res:
            actual = SearchRedReleaseByPrefsModifier.process(si=mock_si, **mock_process_kwargs)
            mock_process_kwargs["red"].browse.assert_called_once()
            mock_tm_from_browse_res.assert_called_once()
            assert actual is mock_si
            if expected_torrent_entry:
                assert isinstance(actual.torrent_entry, TorrentEntry)
            else:
                assert actual.torrent_entry is None
            assert actual.above_max_size_te_found is False

    @pytest.mark.parametrize("is_lfm_rec", [False, True])
    def test_search_red_release_by_prefs_modifier_above_max_size_found(
        self, mock_process_kwargs: _MockProcKwargs, make_album_search_item: pytest.FixtureRequest, is_lfm_rec: bool
    ) -> None:
        mock_red_prefs = [
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.SACD),
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
        ]
        expected_browse_call_cnt = len(mock_red_prefs)
        type(mock_process_kwargs["state"]).red_format_preferences = PropertyMock(return_value=mock_red_prefs)
        mock_si = make_album_search_item(is_lfm_rec=is_lfm_rec)
        assert mock_si.torrent_entry is None
        with patch.object(
            SearchRedReleaseByPrefsModifier,
            "_torrent_match_from_browse_results",
            return_value=TorrentMatch(torrent_entry=None, above_max_size_found=True),
        ) as mock_tm_from_browse_res:
            actual = SearchRedReleaseByPrefsModifier.process(si=mock_si, **mock_process_kwargs)
            assert len(mock_process_kwargs["red"].mock_calls) == expected_browse_call_cnt
            assert len(mock_tm_from_browse_res.mock_calls) == expected_browse_call_cnt
            assert actual is mock_si
            assert actual.torrent_entry is None
            assert actual.above_max_size_te_found is True

    @pytest.mark.parametrize("is_lfm_rec", [False, True])
    def test_search_red_release_by_prefs_modifier_browse_exception_raised(
        self, mock_process_kwargs: _MockProcKwargs, make_album_search_item: pytest.FixtureRequest, is_lfm_rec: bool
    ) -> None:
        mock_red_prefs = [
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.SACD),
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
        ]
        type(mock_process_kwargs["state"]).red_format_preferences = PropertyMock(return_value=mock_red_prefs)
        expected_browse_call_cnt = len(mock_red_prefs)

        def _red_browse_side_effect(*args: Any, **kwargs: Any) -> None:
            raise Exception("Fake exception intentionally raised.")

        mock_process_kwargs["state"].create_red_browse_params.return_value = None
        mock_process_kwargs["red"].browse.side_effect = _red_browse_side_effect
        mock_si = make_album_search_item(is_lfm_rec=is_lfm_rec)
        assert mock_si.torrent_entry is None
        with patch.object(
            SearchRedReleaseByPrefsModifier,
            "_torrent_match_from_browse_results",
            return_value=TorrentMatch(torrent_entry=None, above_max_size_found=True),
        ) as mock_tm_from_browse_res:
            actual = SearchRedReleaseByPrefsModifier.process(si=mock_si, **mock_process_kwargs)
            assert len(mock_process_kwargs["red"].browse.mock_calls) == expected_browse_call_cnt
            mock_tm_from_browse_res.assert_not_called()
            assert actual is mock_si
            assert actual.torrent_entry is None
            assert actual.above_max_size_te_found is False

    @pytest.mark.parametrize(
        "browse_results_te_sizes, state_max_size_gb, expected_found_above_max_size",
        [
            # Test case 1: empty browse results
            ([], 69.0, False),
            # Test case 2: single entry browse results, above size
            ([[420.0]], 69.0, True),
            # Test case 3: multi entry browse results, all above size
            ([[420.0], [42069.0]], 69.0, True),
            # Test case 4: single entry browse results, no torrent entries for browse result
            ([[], []], 69.0, False),
            # Test case 5: multi entry browse results, no torrent entries for either browse result
        ],
    )
    def test_torrent_match_from_browse_results_no_match(
        self,
        make_release_entry: pytest.FixtureRequest,
        mock_te_from_size_factory: pytest.FixtureRequest,
        browse_results_te_sizes: list[list[float]],
        state_max_size_gb: float,
        expected_found_above_max_size: bool,
    ) -> None:
        mock_state = MagicMock(spec=SearchState)
        type(mock_state).max_size_gb = PropertyMock(return_value=state_max_size_gb)
        mock_browse_results = [
            make_release_entry(torrent_entries=[mock_te_from_size_factory(size * 1e9) for size in elem])
            for elem in browse_results_te_sizes
        ]
        actual = SearchRedReleaseByPrefsModifier._torrent_match_from_browse_results(
            browse_results=mock_browse_results, state=mock_state
        )
        assert actual.torrent_entry is None
        assert actual.above_max_size_found is expected_found_above_max_size

    @pytest.mark.parametrize(
        "browse_results_te_sizes, state_max_size_gb, expected_match_size",
        [
            # Test case 1: single entry browse results, under max size
            ([[4.0]], 69.0, 4.0),
            # Test case 2: multi entry browse results, last result under max size
            ([[420.69], [1000.0, 2000.0], [100.0, 20.0]], 69.0, 20.0),
        ],
    )
    def test_torrent_match_from_browse_results_has_match(
        self,
        make_release_entry: pytest.FixtureRequest,
        mock_te_from_size_factory: pytest.FixtureRequest,
        browse_results_te_sizes: list[list[float]],
        state_max_size_gb: float,
        expected_match_size: float,
    ) -> None:
        mock_state = MagicMock(spec=SearchState)
        type(mock_state).max_size_gb = PropertyMock(return_value=state_max_size_gb)
        mock_browse_results = [
            make_release_entry(torrent_entries=[mock_te_from_size_factory(size * 1e9) for size in elem])
            for elem in browse_results_te_sizes
        ]
        actual = SearchRedReleaseByPrefsModifier._torrent_match_from_browse_results(
            browse_results=mock_browse_results, state=mock_state
        )
        assert isinstance(actual.torrent_entry, TorrentEntry)
        assert actual.torrent_entry.size / 1e9 == expected_match_size
        assert not actual.above_max_size_found
