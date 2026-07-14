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


def test_resolve_track_info_modifier_malformed_lfm_blob_falls_through_to_mb(
    mock_process_kwargs: _MockProcKwargs, make_track_search_item: pytest.FixtureRequest
) -> None:
    """
    Regression: a malformed LFM track blob (has an 'album' key but is missing fields construct_from_api_response
    needs) must not crash the modifier — it should be caught and fall through to MusicBrainz resolution.
    """
    mock_process_kwargs["lfm"].get_track_info.return_value = {"album": {}}  # missing 'name'/'artist' -> KeyError
    mock_process_kwargs["mb"].request_release_details_for_track.return_value = {
        "origin_release_mbid": "mbid",
        "origin_release_name": "Resolved Release",
    }
    mock_si = make_track_search_item(is_lfm_rec=True)
    actual = ResolveTrackInfoModifier.process(si=mock_si, **mock_process_kwargs)
    assert isinstance(actual, SearchItem)
    # Fell through to MB (artist_mbid is None since the malformed blob's 'artist' is not a dict).
    mock_process_kwargs["mb"].request_release_details_for_track.assert_called_once_with(si=mock_si, artist_mbid=None)
    assert actual.release_name == "Resolved Release"


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


@pytest.mark.parametrize("is_lfm_rec", [False, True])
def test_attempt_resolve_mb_release_modifier_skips_when_not_required(
    mock_process_kwargs: _MockProcKwargs, make_album_search_item: pytest.FixtureRequest, is_lfm_rec: bool
) -> None:
    """When the config wouldn't use the MB release (no optional search fields enabled), the lookup is skipped."""
    mock_process_kwargs["state"].mb_resolution_would_be_used.return_value = False
    mock_si = make_album_search_item(is_lfm_rec=is_lfm_rec)
    mock_si._lfm_album_info = LFMAlbumInfo(
        artist=mock_si.artist_name, album_name=mock_si.release_name, lfm_url="abc", release_mbid="69-420"
    )
    actual = AttemptResolveMBReleaseModifier.process(si=mock_si, **mock_process_kwargs)
    assert actual is mock_si
    assert actual._mb_release is None
    mock_process_kwargs["mb"].request_release_details.assert_not_called()


class TestSearchRedReleaseByPrefsModifier:
    """A single, format-agnostic browse is issued per rec; ranking the returned torrents against the format
    preferences is delegated to `SearchState.select_best_torrent`."""

    @pytest.mark.parametrize("is_lfm_rec", [False, True])
    def test_single_browse_delegates_ranking(
        self, mock_process_kwargs: _MockProcKwargs, make_album_search_item: pytest.FixtureRequest, is_lfm_rec: bool
    ) -> None:
        matched_te = TorrentEntry(
            torrent_id=69420, media="WEB", format="FLAC", encoding="24bit Lossless", **_MOCK_TE_KWARGS
        )
        release_entries = [MagicMock(spec=ReleaseEntry)]
        mock_process_kwargs["state"].create_red_browse_params.return_value = "browse=params"
        mock_process_kwargs["red"].browse.return_value = release_entries
        mock_process_kwargs["state"].select_best_torrent.return_value = TorrentMatch(
            torrent_entry=matched_te, above_max_size_found=False
        )
        mock_si = make_album_search_item(is_lfm_rec=is_lfm_rec)
        assert mock_si.torrent_entry is None
        actual = SearchRedReleaseByPrefsModifier.process(si=mock_si, **mock_process_kwargs)
        mock_process_kwargs["state"].create_red_browse_params.assert_called_once_with(si=mock_si)
        mock_process_kwargs["red"].browse.assert_called_once_with(request_params="browse=params")
        mock_process_kwargs["state"].select_best_torrent.assert_called_once_with(release_entries=release_entries)
        assert actual is mock_si
        assert actual.torrent_entry is matched_te
        assert actual.above_max_size_te_found is False

    @pytest.mark.parametrize("is_lfm_rec", [False, True])
    def test_no_match_records_above_max_size(
        self, mock_process_kwargs: _MockProcKwargs, make_album_search_item: pytest.FixtureRequest, is_lfm_rec: bool
    ) -> None:
        mock_process_kwargs["red"].browse.return_value = []
        mock_process_kwargs["state"].select_best_torrent.return_value = TorrentMatch(
            torrent_entry=None, above_max_size_found=True
        )
        mock_si = make_album_search_item(is_lfm_rec=is_lfm_rec)
        actual = SearchRedReleaseByPrefsModifier.process(si=mock_si, **mock_process_kwargs)
        assert actual is mock_si
        assert actual.torrent_entry is None
        assert actual.above_max_size_te_found is True

    @pytest.mark.parametrize("is_lfm_rec", [False, True])
    def test_browse_exception_ranks_empty_results(
        self, mock_process_kwargs: _MockProcKwargs, make_album_search_item: pytest.FixtureRequest, is_lfm_rec: bool
    ) -> None:
        """A failed browse is logged and treated as empty results, which the ranker turns into a no-match."""

        def _raise(*args: Any, **kwargs: Any) -> None:
            raise Exception("Fake exception intentionally raised.")

        mock_process_kwargs["red"].browse.side_effect = _raise
        mock_process_kwargs["state"].select_best_torrent.return_value = TorrentMatch(
            torrent_entry=None, above_max_size_found=False
        )
        mock_si = make_album_search_item(is_lfm_rec=is_lfm_rec)
        actual = SearchRedReleaseByPrefsModifier.process(si=mock_si, **mock_process_kwargs)
        mock_process_kwargs["state"].select_best_torrent.assert_called_once_with(release_entries=[])
        assert actual is mock_si
        assert actual.torrent_entry is None
        assert actual.above_max_size_te_found is False
