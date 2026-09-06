from typing import Any, TypedDict
from unittest.mock import MagicMock, patch

import pytest

from plastered.db.db_models import SearchRecord
from plastered.models import (
    EntityType,
    LFMAlbumInfo,
    MBRelease,
    OriginRelease,
    OriginSource,
    ReleaseEntry,
    SearchItem,
    SearchStage,
    SearchStepOutcome,
    TorrentEntry,
    TorrentMatch,
    TraceStep,
)
from plastered.release_search.processors.modifiers import (
    ResolveAlbumInfoModifier,
    ResolveTrackOriginModifier,
    AttachSearchIdModifier,
    AttemptResolveMBReleaseModifier,
    SearchRedReleaseByPrefsModifier,
    _describe_mb_release,
    _describe_origin_candidates,
    _lfm_failure_detail,
    _request_release_details_with_fallback,
)
from plastered.release_search.processors.bases import SearchItemModifier
from plastered.release_search.search_helpers import SearchState
from plastered.utils.exceptions import (
    LFMClientException,
    LFMRequestFailureException,
    MusicBrainzClientException,
    MusicBrainzRequestFailureException,
)
from plastered.utils.http_clients import LFMAPIClient, MusicBrainzAPIClient, RedAPIClient
from plastered.utils.constants import MUSICBRAINZ_LOOKUP_LINKED_ENTITY_CAP

_UPSERT_RESOLVED_ORIGIN = "plastered.release_search.processors.modifiers.upsert_resolved_origin"


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


def _origin(
    name: str,
    source: OriginSource = OriginSource.MB_RECORDING_LOOKUP,
    mbid: str | None = None,
    primary_type: str | None = "Album",
    date: str | None = "2000",
) -> OriginRelease:
    return OriginRelease(
        release_name=name, source=source, release_mbid=mbid, primary_type=primary_type, release_date=date
    )


@pytest.mark.parametrize("entity_type", [et for et in EntityType])
@pytest.mark.parametrize(
    "filter_class",
    [
        ResolveAlbumInfoModifier,
        ResolveTrackOriginModifier,
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
    if filter_class == ResolveTrackOriginModifier and entity_type == EntityType.ALBUM:
        pytest.skip(f"{ResolveTrackOriginModifier.__class__.__qualname__} not relevant for albums.")
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
    assert mock_si.origin_candidates == []
    with patch.object(
        LFMAlbumInfo, "construct_from_api_response", return_value=mock_lfmai
    ) as mock_construct_from_api_response:
        actual = ResolveAlbumInfoModifier.process(si=mock_si, **mock_process_kwargs)
        assert actual is mock_si
        if is_lfm_rec:
            mock_construct_from_api_response.assert_called_once()
            assert actual._lfm_album_info is not None
            assert actual.trace == [
                TraceStep(
                    stage=SearchStage.LFM_ALBUM_INFO,
                    outcome=SearchStepOutcome.OK,
                    detail='Last.fm album info found (release MBID "1234")',
                )
            ]
        else:
            mock_construct_from_api_response.assert_not_called()
            assert actual._lfm_album_info is None
            assert actual.trace == []


def test_resolve_album_info_modifier_traces_a_missing_mbid(
    mock_process_kwargs: _MockProcKwargs, make_album_search_item: pytest.FixtureRequest
) -> None:
    mbidless = LFMAlbumInfo(artist="Foo", release_mbid=None, album_name="Bar", lfm_url="https://blah.com")
    with patch.object(LFMAlbumInfo, "construct_from_api_response", return_value=mbidless):
        actual = ResolveAlbumInfoModifier.process(si=make_album_search_item(is_lfm_rec=True), **mock_process_kwargs)
    assert actual.trace[0].detail == "Last.fm album info found (no release MBID)"


@pytest.mark.parametrize(
    "raised_exception, expected_lfm_request_failed",
    [
        (LFMClientException("Intentionally raised exception"), False),
        (LFMRequestFailureException("Intentionally raised exception"), True),
    ],
)
def test_resolve_album_info_modifier_lfm_exception(
    mock_process_kwargs: _MockProcKwargs,
    make_album_search_item: pytest.FixtureRequest,
    raised_exception: LFMClientException,
    expected_lfm_request_failed: bool,
) -> None:
    """An LFM client error degrades to no album info; only an infra-level failure sets `lfm_request_failed`."""
    mock_process_kwargs["lfm"].get_album_info.side_effect = raised_exception
    mock_si = make_album_search_item(is_lfm_rec=True)
    actual = ResolveAlbumInfoModifier.process(si=mock_si, **mock_process_kwargs)
    assert actual is mock_si
    assert actual._lfm_album_info is None
    assert actual.lfm_request_failed is expected_lfm_request_failed
    assert actual.trace == [
        TraceStep(
            stage=SearchStage.LFM_ALBUM_INFO,
            outcome=SearchStepOutcome.WARNING,
            detail=(
                "Last.fm request failed"
                if expected_lfm_request_failed
                else "Last.fm album lookup failed: Intentionally raised exception"
            ),
        )
    ]


def test_lfm_failure_detail() -> None:
    assert _lfm_failure_detail(ex=LFMRequestFailureException("x"), lookup="track") == "Last.fm request failed"
    assert _lfm_failure_detail(ex=LFMClientException("boom"), lookup="album") == "Last.fm album lookup failed: boom"
    assert _lfm_failure_detail(ex=KeyError("album"), lookup="track") == "Last.fm returned an unusable track payload"


class TestResolveTrackOriginModifier:
    """The LFM album and the MB recording lookup / search results are gathered and ranked into origin candidates."""

    @pytest.fixture
    def lookup_candidates(self) -> list[OriginRelease]:
        return [
            _origin("Blue Flowers", mbid="single-mbid", primary_type="Single", date="1996"),
            _origin("Dr. Octagonecologyst", mbid="album-mbid", date="1996-05-07"),
        ]

    @pytest.mark.parametrize("is_lfm_rec", [False, True])
    def test_lookup_by_lfm_recording_mbid(
        self,
        mock_full_lfm_track_info_json: dict[str, Any],
        mock_process_kwargs: _MockProcKwargs,
        make_track_search_item: pytest.FixtureRequest,
        lookup_candidates: list[OriginRelease],
        is_lfm_rec: bool,
    ) -> None:
        """A full LFM blob drives a recording lookup (no search); the LFM album folds into the ranked MB album."""
        si = make_track_search_item(is_lfm_rec=is_lfm_rec, artist="Dr. Octagon", track="No Awareness")
        si.search_id = 7
        lfm_resp = mock_full_lfm_track_info_json["track"]
        mock_process_kwargs["lfm"].get_track_info.return_value = lfm_resp
        mock_process_kwargs["mb"].lookup_recording_origin_releases.return_value = lookup_candidates
        with patch(_UPSERT_RESOLVED_ORIGIN) as mock_upsert:
            actual = ResolveTrackOriginModifier.process(si=si, **mock_process_kwargs)
        assert actual is si
        mock_process_kwargs["lfm"].get_track_info.assert_called_once_with(si=si)
        mock_process_kwargs["mb"].lookup_recording_origin_releases.assert_called_once_with(
            recording_mbid=lfm_resp["mbid"], artist_name="Dr. Octagon", artist_mbid=lfm_resp["artist"]["mbid"]
        )
        mock_process_kwargs["mb"].search_recording_origin_releases.assert_not_called()
        assert [c.release_name for c in actual.origin_candidates] == ["Dr. Octagonecologyst", "Blue Flowers"]
        assert actual.release_name == "Dr. Octagonecologyst"
        assert actual.top_origin is lookup_candidates[1]
        mock_upsert.assert_called_once_with(
            search_id=7, origin=lookup_candidates[1], candidate_rank=0, candidate_count=2, matched=False
        )
        assert actual.lfm_request_failed is False and actual.mb_request_failed is False
        assert actual.trace == [
            TraceStep(
                stage=SearchStage.LFM_TRACK_INFO,
                outcome=SearchStepOutcome.OK,
                detail='Last.fm lists the track on "Dr. Octagonecologyst"',
            ),
            TraceStep(
                stage=SearchStage.MB_RECORDING,
                outcome=SearchStepOutcome.OK,
                detail="MusicBrainz lists 2 releases for the recording (recording lookup by MBID)",
            ),
            TraceStep(
                stage=SearchStage.TRACK_ORIGIN,
                outcome=SearchStepOutcome.OK,
                detail=(
                    '2 candidate origin releases, best first: "Dr. Octagonecologyst" (album, 1996), '
                    '"Blue Flowers" (single, 1996)'
                ),
            ),
        ]

    def test_search_fallback_when_lookup_is_empty(
        self,
        mock_full_lfm_track_info_json: dict[str, Any],
        mock_process_kwargs: _MockProcKwargs,
        make_track_search_item: pytest.FixtureRequest,
    ) -> None:
        """An empty lookup (stale MBID / artist mismatch) falls back to the recording search."""
        si = make_track_search_item(is_lfm_rec=True, artist="Dr. Octagon", track="No Awareness")
        lfm_resp = mock_full_lfm_track_info_json["track"]
        single = _origin("Blue Flowers", source=OriginSource.MB_RECORDING_SEARCH, primary_type="Single")
        mock_process_kwargs["lfm"].get_track_info.return_value = lfm_resp
        mock_process_kwargs["mb"].lookup_recording_origin_releases.return_value = []
        mock_process_kwargs["mb"].search_recording_origin_releases.return_value = [single]
        with patch(_UPSERT_RESOLVED_ORIGIN):
            actual = ResolveTrackOriginModifier.process(si=si, **mock_process_kwargs)
        mock_process_kwargs["mb"].search_recording_origin_releases.assert_called_once_with(
            track_name="No Awareness", artist_name="Dr. Octagon", artist_mbid=lfm_resp["artist"]["mbid"]
        )
        # The single ranks first; the (type-less) LFM album is kept as a last-tier candidate of its own.
        assert [(c.release_name, c.source) for c in actual.origin_candidates] == [
            ("Blue Flowers", OriginSource.MB_RECORDING_SEARCH),
            ("Dr. Octagonecologyst", OriginSource.LFM),
        ]
        assert actual.trace[1].detail == (
            "MusicBrainz lists 1 release for the recording (recording lookup by MBID + recording search)"
        )
        assert actual.trace[2].detail == (
            '2 candidate origin releases, best first: "Blue Flowers" (single, 2000), "Dr. Octagonecologyst"'
        )

    def test_capped_lookup_also_searches_and_merges(
        self,
        mock_full_lfm_track_info_json: dict[str, Any],
        mock_process_kwargs: _MockProcKwargs,
        make_track_search_item: pytest.FixtureRequest,
    ) -> None:
        """A lookup listing at MB's linked-entity cap may lack the original album, so the search results are merged."""
        si = make_track_search_item(is_lfm_rec=True, artist="Dr. Octagon", track="No Awareness")
        capped_listing = [
            OriginRelease(
                release_name=f"Album {i}",
                source=OriginSource.MB_RECORDING_LOOKUP,
                release_group_mbid=f"rg-{i}",
                primary_type="Album",
                release_date=str(2000 + i),
            )
            for i in range(MUSICBRAINZ_LOOKUP_LINKED_ENTITY_CAP)
        ]
        original_album = _origin("Dr. Octagonecologyst", source=OriginSource.MB_RECORDING_SEARCH, date="1996")
        mock_process_kwargs["lfm"].get_track_info.return_value = mock_full_lfm_track_info_json["track"]
        mock_process_kwargs["mb"].lookup_recording_origin_releases.return_value = capped_listing
        mock_process_kwargs["mb"].search_recording_origin_releases.return_value = [original_album]
        with patch(_UPSERT_RESOLVED_ORIGIN):
            actual = ResolveTrackOriginModifier.process(si=si, **mock_process_kwargs)
        mock_process_kwargs["mb"].search_recording_origin_releases.assert_called_once()
        assert actual.top_origin is original_album
        assert len(actual.origin_candidates) == MUSICBRAINZ_LOOKUP_LINKED_ENTITY_CAP + 1

    def test_no_album_lfm_blob_searches_without_lookup(
        self,
        mock_no_album_lfm_track_info_json: dict[str, Any],
        mock_process_kwargs: _MockProcKwargs,
        make_track_search_item: pytest.FixtureRequest,
    ) -> None:
        """Without a recording MBID from LFM only the search runs; no candidates leaves the item unresolved."""
        si = make_track_search_item(is_lfm_rec=True, artist="The Tuss", track="rushup i bank 12 M")
        lfm_resp = mock_no_album_lfm_track_info_json["track"]
        mock_process_kwargs["lfm"].get_track_info.return_value = lfm_resp
        mock_process_kwargs["mb"].search_recording_origin_releases.return_value = []
        with patch(_UPSERT_RESOLVED_ORIGIN) as mock_upsert:
            actual = ResolveTrackOriginModifier.process(si=si, **mock_process_kwargs)
        mock_process_kwargs["mb"].lookup_recording_origin_releases.assert_not_called()
        mock_process_kwargs["mb"].search_recording_origin_releases.assert_called_once_with(
            track_name="rushup i bank 12 M", artist_name="The Tuss", artist_mbid=lfm_resp["artist"]["mbid"]
        )
        assert actual.origin_candidates == [] and actual.release_name == "None"
        mock_upsert.assert_not_called()
        # Nothing was gathered, so the stop (traced by the following filter) needs no origin step of its own.
        assert actual.trace == [
            TraceStep(
                stage=SearchStage.LFM_TRACK_INFO,
                outcome=SearchStepOutcome.WARNING,
                detail="Last.fm lists no release for the track",
            ),
            TraceStep(
                stage=SearchStage.MB_RECORDING,
                outcome=SearchStepOutcome.WARNING,
                detail=(
                    'MusicBrainz lists no release for a recording of "rushup i bank 12 M" by "The Tuss" '
                    "(recording search)"
                ),
            ),
        ]

    def test_only_non_origin_releases_gathered_traces_why_no_candidate_stands(
        self,
        mock_full_lfm_track_info_json: dict[str, Any],
        mock_process_kwargs: _MockProcKwargs,
        make_track_search_item: pytest.FixtureRequest,
    ) -> None:
        """The LFM album folds into MB's same-titled compilation, which is no origin type: no candidate remains."""
        si = make_track_search_item(is_lfm_rec=True, artist="Dr. Octagon", track="No Awareness")
        compilation = OriginRelease(
            release_name="Dr. Octagonecologyst",
            source=OriginSource.MB_RECORDING_LOOKUP,
            primary_type="Album",
            secondary_types=("Compilation",),
            release_date="1996",
        )
        mock_process_kwargs["lfm"].get_track_info.return_value = mock_full_lfm_track_info_json["track"]
        mock_process_kwargs["mb"].lookup_recording_origin_releases.return_value = [compilation]
        with patch(_UPSERT_RESOLVED_ORIGIN):
            actual = ResolveTrackOriginModifier.process(si=si, **mock_process_kwargs)
        assert actual.origin_candidates == []
        assert actual.trace[-1] == TraceStep(
            stage=SearchStage.TRACK_ORIGIN,
            outcome=SearchStepOutcome.WARNING,
            detail="None of the gathered releases is an album / EP / single / soundtrack",
        )

    @pytest.mark.parametrize(
        "raised_exception, expected_lfm_request_failed",
        [
            (LFMClientException("Intentionally raised exception"), False),
            (LFMRequestFailureException("Intentionally raised exception"), True),
        ],
    )
    def test_lfm_exception_still_searches(
        self,
        mock_process_kwargs: _MockProcKwargs,
        make_track_search_item: pytest.FixtureRequest,
        raised_exception: LFMClientException,
        expected_lfm_request_failed: bool,
    ) -> None:
        """An LFM failure only flags the item (infra-level failures); the MB search still resolves candidates."""
        si = make_track_search_item(is_lfm_rec=True)
        mock_process_kwargs["lfm"].get_track_info.side_effect = raised_exception
        album = _origin("Album", source=OriginSource.MB_RECORDING_SEARCH)
        mock_process_kwargs["mb"].search_recording_origin_releases.return_value = [album]
        with patch(_UPSERT_RESOLVED_ORIGIN):
            actual = ResolveTrackOriginModifier.process(si=si, **mock_process_kwargs)
        mock_process_kwargs["mb"].search_recording_origin_releases.assert_called_once_with(
            track_name=si.track_name, artist_name=si.artist_name, artist_mbid=None
        )
        assert actual.origin_candidates == [album] and actual.release_name == "Album"
        assert actual.lfm_request_failed is expected_lfm_request_failed
        assert actual.mb_request_failed is False

    def test_malformed_lfm_blob_falls_through_to_search(
        self, mock_process_kwargs: _MockProcKwargs, make_track_search_item: pytest.FixtureRequest
    ) -> None:
        si = make_track_search_item(is_lfm_rec=True)
        mock_process_kwargs["lfm"].get_track_info.return_value = "not-a-dict"
        mock_process_kwargs["mb"].search_recording_origin_releases.return_value = []
        with patch(_UPSERT_RESOLVED_ORIGIN):
            actual = ResolveTrackOriginModifier.process(si=si, **mock_process_kwargs)
        mock_process_kwargs["mb"].search_recording_origin_releases.assert_called_once_with(
            track_name=si.track_name, artist_name=si.artist_name, artist_mbid=None
        )
        assert actual.origin_candidates == [] and actual.lfm_request_failed is False

    def test_mb_request_failure_keeps_lfm_candidate(
        self,
        mock_full_lfm_track_info_json: dict[str, Any],
        mock_process_kwargs: _MockProcKwargs,
        make_track_search_item: pytest.FixtureRequest,
    ) -> None:
        """An infra-level MB failure flags the item; the LFM album still stands as the only candidate."""
        si = make_track_search_item(is_lfm_rec=True, artist="Dr. Octagon", track="No Awareness")
        si.search_id = 9
        mock_process_kwargs["lfm"].get_track_info.return_value = mock_full_lfm_track_info_json["track"]
        mock_process_kwargs["mb"].lookup_recording_origin_releases.side_effect = MusicBrainzRequestFailureException(
            "Intentionally raised exception"
        )
        with patch(_UPSERT_RESOLVED_ORIGIN) as mock_upsert:
            actual = ResolveTrackOriginModifier.process(si=si, **mock_process_kwargs)
        mock_process_kwargs["mb"].search_recording_origin_releases.assert_not_called()
        assert actual.mb_request_failed is True
        assert [(c.release_name, c.source) for c in actual.origin_candidates] == [
            ("Dr. Octagonecologyst", OriginSource.LFM)
        ]
        mock_upsert.assert_called_once_with(
            search_id=9, origin=actual.origin_candidates[0], candidate_rank=0, candidate_count=1, matched=False
        )
        assert actual.trace[1:] == [
            TraceStep(
                stage=SearchStage.MB_RECORDING,
                outcome=SearchStepOutcome.WARNING,
                detail="MusicBrainz request failed (recording lookup by MBID)",
            ),
            TraceStep(
                stage=SearchStage.TRACK_ORIGIN,
                outcome=SearchStepOutcome.OK,
                detail='1 candidate origin release, best first: "Dr. Octagonecologyst"',
            ),
        ]

    def test_search_request_failure_sets_flag(
        self, mock_process_kwargs: _MockProcKwargs, make_track_search_item: pytest.FixtureRequest
    ) -> None:
        si = make_track_search_item(is_lfm_rec=True)
        mock_process_kwargs["lfm"].get_track_info.return_value = {"no_album_key": True}
        mock_process_kwargs["mb"].search_recording_origin_releases.side_effect = MusicBrainzRequestFailureException(
            "Intentionally raised exception"
        )
        with patch(_UPSERT_RESOLVED_ORIGIN) as mock_upsert:
            actual = ResolveTrackOriginModifier.process(si=si, **mock_process_kwargs)
        assert actual.mb_request_failed is True
        assert actual.origin_candidates == []
        mock_upsert.assert_not_called()


def test_describe_origin_candidates_names_the_top_few() -> None:
    candidates = [_origin(f"Album {i}", date=str(2000 + i)) for i in range(7)]
    assert _describe_origin_candidates(candidates=candidates) == (
        '7 candidate origin releases, best first: "Album 0" (album, 2000), "Album 1" (album, 2001), '
        '"Album 2" (album, 2002), "Album 3" (album, 2003), "Album 4" (album, 2004), … and 2 more'
    )
    assert _describe_origin_candidates(candidates=candidates[:1]) == (
        '1 candidate origin release, best first: "Album 0" (album, 2000)'
    )


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


def _attach_lfm_mbid(si: SearchItem, entity_type: EntityType, mbid: str | None) -> None:
    """Gives the item an LFM-sourced release MBID: album info for albums, a top origin candidate for tracks."""
    if entity_type == EntityType.TRACK:
        si.set_origin_candidates([_origin(si.release_name, source=OriginSource.LFM, mbid=mbid, primary_type=None)])
    else:
        si._lfm_album_info = LFMAlbumInfo(
            artist=si.artist_name, album_name=si.release_name, lfm_url="abc", release_mbid=mbid
        )


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
    _attach_lfm_mbid(si=si, entity_type=entity_type, mbid=mock_matched_mbid)
    # With no LFM-provided MBID, the modifier falls back to the MB release search; a fruitless search leaves the
    # item unresolved.
    mock_process_kwargs["mb"].search_release_mbid.return_value = None
    expected_mb_release = (
        MBRelease.construct_from_api(json_blob=mock_musicbrainz_release_json) if has_matched_mbid else None
    )
    mock_process_kwargs["mb"].request_release_details.return_value = mock_musicbrainz_release_json
    actual = AttemptResolveMBReleaseModifier.process(si=si, **mock_process_kwargs)
    assert actual is si
    assert actual._mb_release == expected_mb_release
    if has_matched_mbid:
        mock_process_kwargs["mb"].search_release_mbid.assert_not_called()
        mock_process_kwargs["mb"].request_release_details.assert_called_once_with(mbid=mock_matched_mbid)
        assert actual.trace == [
            TraceStep(
                stage=SearchStage.MB_RELEASE,
                outcome=SearchStepOutcome.OK,
                detail=(
                    'Resolved MusicBrainz release "Dr. Octagonecologyst" (MBID d211379d-3203-47ed-a0c5-e564815bb45a, '
                    'via MBID lookup): type album, year 1996, label "Get On Down", catalogue number "58010"'
                ),
            )
        ]
    else:
        mock_process_kwargs["mb"].search_release_mbid.assert_called_once_with(
            artist_name=si.artist_name, release_name=si.release_name
        )
        mock_process_kwargs["mb"].request_release_details.assert_not_called()
        assert actual.trace == [
            TraceStep(
                stage=SearchStage.MB_RELEASE,
                outcome=SearchStepOutcome.WARNING,
                detail=(
                    f'No MusicBrainz release found for "{si.release_name}" by "{si.artist_name}"; continuing without '
                    "release details"
                ),
            )
        ]


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize("is_lfm_rec", [False, True])
def test_attempt_resolve_mb_release_modifier_search_fallback_resolves(
    mock_musicbrainz_release_json: dict[str, Any],
    mock_process_kwargs: _MockProcKwargs,
    make_album_search_item: pytest.FixtureRequest,
    is_lfm_rec: bool,
) -> None:
    """An item with no LFM MBID resolves its MB release via the release-search fallback."""
    mock_si = make_album_search_item(is_lfm_rec=is_lfm_rec)
    mock_process_kwargs["mb"].search_release_mbid.return_value = "searched-mbid"
    mock_process_kwargs["mb"].request_release_details.return_value = mock_musicbrainz_release_json
    actual = AttemptResolveMBReleaseModifier.process(si=mock_si, **mock_process_kwargs)
    assert actual is mock_si
    assert actual._mb_release == MBRelease.construct_from_api(json_blob=mock_musicbrainz_release_json)
    mock_process_kwargs["mb"].search_release_mbid.assert_called_once_with(
        artist_name=mock_si.artist_name, release_name=mock_si.release_name
    )
    mock_process_kwargs["mb"].request_release_details.assert_called_once_with(mbid="searched-mbid")
    assert len(actual.trace) == 1 and actual.trace[0].outcome == SearchStepOutcome.OK
    assert "(MBID d211379d-3203-47ed-a0c5-e564815bb45a, via release search)" in actual.trace[0].detail


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize("entity_type", [et for et in EntityType])
def test_attempt_resolve_mb_release_modifier_stale_mbid_falls_back_to_search(
    mock_musicbrainz_release_json: dict[str, Any],
    mock_process_kwargs: _MockProcKwargs,
    make_album_search_item: pytest.FixtureRequest,
    make_track_search_item: pytest.FixtureRequest,
    entity_type: EntityType,
) -> None:
    """An LFM-supplied MBID that MB answers with an error is replaced via the release search, then looked up."""
    si = make_album_search_item(is_lfm_rec=True) if entity_type == EntityType.ALBUM else make_track_search_item(True)
    _attach_lfm_mbid(si=si, entity_type=entity_type, mbid="stale-mbid")
    mock_process_kwargs["mb"].request_release_details.side_effect = [
        MusicBrainzClientException("404"),
        mock_musicbrainz_release_json,
    ]
    mock_process_kwargs["mb"].search_release_mbid.return_value = "searched-mbid"
    actual = AttemptResolveMBReleaseModifier.process(si=si, **mock_process_kwargs)
    assert actual._mb_release == MBRelease.construct_from_api(json_blob=mock_musicbrainz_release_json)
    assert actual.mb_request_failed is False
    assert [c.kwargs["mbid"] for c in mock_process_kwargs["mb"].request_release_details.call_args_list] == [
        "stale-mbid",
        "searched-mbid",
    ]
    mock_process_kwargs["mb"].search_release_mbid.assert_called_once_with(
        artist_name=si.artist_name, release_name=si.release_name
    )
    assert [(step.stage, step.outcome) for step in actual.trace] == [
        (SearchStage.MB_RELEASE, SearchStepOutcome.WARNING),
        (SearchStage.MB_RELEASE, SearchStepOutcome.OK),
    ]
    assert actual.trace[0].detail == (
        'MusicBrainz does not serve release MBID "stale-mbid"; searching for the release instead'
    )
    assert "via release search" in actual.trace[1].detail


def test_attempt_resolve_mb_release_modifier_search_fallback_request_failure(
    mock_process_kwargs: _MockProcKwargs, make_album_search_item: pytest.FixtureRequest
) -> None:
    """An infra-level failure during the MB release-search fallback sets `mb_request_failed` and stops resolution."""
    mock_si = make_album_search_item(is_lfm_rec=True)
    mock_process_kwargs["mb"].search_release_mbid.side_effect = MusicBrainzRequestFailureException(
        "Intentionally raised exception"
    )
    actual = AttemptResolveMBReleaseModifier.process(si=mock_si, **mock_process_kwargs)
    assert actual is mock_si
    assert actual.mb_request_failed is True
    assert actual._mb_release is None
    mock_process_kwargs["mb"].request_release_details.assert_not_called()
    assert actual.trace == [
        TraceStep(
            stage=SearchStage.MB_RELEASE,
            outcome=SearchStepOutcome.WARNING,
            detail="MusicBrainz request failed; continuing without release details",
        )
    ]


def test_attempt_resolve_mb_release_modifier_malformed_release_payload(
    mock_process_kwargs: _MockProcKwargs, make_album_search_item: pytest.FixtureRequest
) -> None:
    """A release payload missing expected keys is logged and leaves the item unresolved rather than crashing."""
    mock_si = make_album_search_item(is_lfm_rec=True)
    _attach_lfm_mbid(si=mock_si, entity_type=EntityType.ALBUM, mbid="69-420")
    mock_process_kwargs["mb"].request_release_details.return_value = {}
    actual = AttemptResolveMBReleaseModifier.process(si=mock_si, **mock_process_kwargs)
    assert actual._mb_release is None and actual.mb_request_failed is False
    assert actual.trace == [
        TraceStep(
            stage=SearchStage.MB_RELEASE,
            outcome=SearchStepOutcome.WARNING,
            detail="Malformed MusicBrainz release payload; continuing without release details",
        )
    ]


def test_request_release_details_with_fallback_no_search_result(
    mock_process_kwargs: _MockProcKwargs, make_album_search_item: pytest.FixtureRequest
) -> None:
    mock_si = make_album_search_item(is_lfm_rec=True)
    mock_process_kwargs["mb"].search_release_mbid.return_value = None
    assert _request_release_details_with_fallback(si=mock_si, mb=mock_process_kwargs["mb"], mbid=None) == (
        None,
        "release search",
    )
    mock_process_kwargs["mb"].request_release_details.assert_not_called()
    assert mock_si.trace == []


def test_describe_mb_release_without_optional_fields() -> None:
    bare = MBRelease(
        mbid="m", title="T", artist="a", primary_type="Other", release_date="2020", release_group_mbid="rg"
    )
    assert _describe_mb_release(mbr=bare, via="MBID lookup") == (
        'Resolved MusicBrainz release "T" (MBID m, via MBID lookup): no release type, year, label or catalogue number'
    )


@pytest.mark.parametrize(
    "raised_exception, expected_mb_request_failed",
    [
        (MusicBrainzClientException("Intentionally raised exception"), False),
        (MusicBrainzRequestFailureException("Intentionally raised exception"), True),
    ],
)
@pytest.mark.parametrize("is_lfm_rec", [False, True])
@pytest.mark.parametrize("entity_type", [et for et in EntityType])
def test_attempt_resolve_mb_release_modifier_exception(
    mock_process_kwargs: _MockProcKwargs,
    make_album_search_item: pytest.FixtureRequest,
    make_track_search_item: pytest.FixtureRequest,
    is_lfm_rec: bool,
    entity_type: EntityType,
    raised_exception: MusicBrainzClientException,
    expected_mb_request_failed: bool,
) -> None:
    mock_si = (
        make_album_search_item(is_lfm_rec=is_lfm_rec)
        if entity_type == EntityType.ALBUM
        else make_track_search_item(is_lfm_rec=is_lfm_rec)
    )
    _attach_lfm_mbid(si=mock_si, entity_type=entity_type, mbid="69-420")
    mock_process_kwargs["mb"].request_release_details.side_effect = raised_exception
    actual = AttemptResolveMBReleaseModifier.process(si=mock_si, **mock_process_kwargs)
    assert isinstance(actual, SearchItem)
    assert actual._mb_release is None
    assert actual.mb_request_failed is expected_mb_request_failed
    # A request failure stops resolution at the MBID lookup; an error response falls back to the release search,
    # whose looked-up MBID errors too (the mock raises on every lookup).
    assert [step.outcome for step in actual.trace] == [SearchStepOutcome.WARNING] * (
        1 if expected_mb_request_failed else 2
    )
    assert actual.trace[-1].detail == (
        "MusicBrainz request failed; continuing without release details"
        if expected_mb_request_failed
        else "MusicBrainz returned an error for the release; continuing without release details"
    )


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
    assert actual.trace == []


class TestSearchRedReleaseByPrefsModifier:
    """A single artist-endpoint request is issued per rec; matching the wanted release against the listing and
    ranking the candidates' torrents against the format preferences are delegated to `SearchState`."""

    @pytest.mark.parametrize("is_lfm_rec", [False, True])
    def test_single_artist_request_delegates_matching_and_ranking(
        self, mock_process_kwargs: _MockProcKwargs, make_album_search_item: pytest.FixtureRequest, is_lfm_rec: bool
    ) -> None:
        matched_te = TorrentEntry(
            torrent_id=69420, media="WEB", format="FLAC", encoding="24bit Lossless", **_MOCK_TE_KWARGS
        )
        release_entries = [MagicMock(spec=ReleaseEntry), MagicMock(spec=ReleaseEntry)]
        mock_process_kwargs["state"].get_cached_artist_release_groups.return_value = None  # cache miss
        mock_process_kwargs["red"].get_artist_release_groups.return_value = release_entries
        mock_process_kwargs["state"].match_album_release.return_value = TorrentMatch(
            torrent_entry=matched_te, above_max_size_found=False
        )
        mock_si = make_album_search_item(is_lfm_rec=is_lfm_rec)
        assert mock_si.torrent_entry is None
        with patch(_UPSERT_RESOLVED_ORIGIN) as mock_upsert:
            actual = SearchRedReleaseByPrefsModifier.process(si=mock_si, **mock_process_kwargs)
        mock_process_kwargs["red"].get_artist_release_groups.assert_called_once_with(artist_name=mock_si.artist_name)
        # The fetched listing is cached on the run state for later recs by the same artist.
        mock_process_kwargs["state"].cache_artist_release_groups.assert_called_once_with(
            artist_name=mock_si.artist_name, release_entries=release_entries
        )
        mock_process_kwargs["state"].match_album_release.assert_called_once_with(
            si=mock_si, release_entries=release_entries
        )
        mock_process_kwargs["state"].match_track_origin_candidates.assert_not_called()
        mock_upsert.assert_not_called()
        assert actual is mock_si
        assert actual.torrent_entry is matched_te
        assert actual.above_max_size_te_found is False
        assert actual.trace == [
            TraceStep(
                stage=SearchStage.RED_ARTIST,
                outcome=SearchStepOutcome.OK,
                detail='RED lists 2 release groups for artist "artist"',
            )
        ]

    @pytest.mark.parametrize("is_lfm_rec", [False, True])
    def test_cached_artist_listing_skips_the_red_request(
        self, mock_process_kwargs: _MockProcKwargs, make_album_search_item: pytest.FixtureRequest, is_lfm_rec: bool
    ) -> None:
        """A run-cached artist listing is reused: no RED request is issued and nothing is re-cached."""
        cached_entries = [MagicMock(spec=ReleaseEntry)]
        mock_process_kwargs["state"].get_cached_artist_release_groups.return_value = cached_entries
        mock_process_kwargs["state"].match_album_release.return_value = TorrentMatch(
            torrent_entry=None, above_max_size_found=False
        )
        mock_si = make_album_search_item(is_lfm_rec=is_lfm_rec)
        actual = SearchRedReleaseByPrefsModifier.process(si=mock_si, **mock_process_kwargs)
        mock_process_kwargs["red"].get_artist_release_groups.assert_not_called()
        mock_process_kwargs["state"].cache_artist_release_groups.assert_not_called()
        mock_process_kwargs["state"].match_album_release.assert_called_once_with(
            si=mock_si, release_entries=cached_entries
        )
        assert actual is mock_si
        assert actual.trace[0].detail == 'RED lists 1 release group for artist "artist"'

    @pytest.mark.parametrize("is_lfm_rec", [False, True])
    def test_no_match_records_above_max_size(
        self, mock_process_kwargs: _MockProcKwargs, make_album_search_item: pytest.FixtureRequest, is_lfm_rec: bool
    ) -> None:
        mock_process_kwargs["state"].get_cached_artist_release_groups.return_value = None  # cache miss
        mock_process_kwargs["red"].get_artist_release_groups.return_value = []
        mock_process_kwargs["state"].match_album_release.return_value = TorrentMatch(
            torrent_entry=None, above_max_size_found=True
        )
        mock_si = make_album_search_item(is_lfm_rec=is_lfm_rec)
        actual = SearchRedReleaseByPrefsModifier.process(si=mock_si, **mock_process_kwargs)
        assert actual is mock_si
        assert actual.torrent_entry is None
        assert actual.above_max_size_te_found is True
        # An unknown artist (an empty listing) is cached like any other listing, and traced as a warning.
        mock_process_kwargs["state"].cache_artist_release_groups.assert_called_once_with(
            artist_name=mock_si.artist_name, release_entries=[]
        )
        assert actual.trace == [
            TraceStep(
                stage=SearchStage.RED_ARTIST,
                outcome=SearchStepOutcome.WARNING,
                detail='RED lists no release groups for artist "artist"',
            )
        ]

    @pytest.mark.parametrize("is_lfm_rec", [False, True])
    def test_artist_request_exception_ranks_empty_results(
        self, mock_process_kwargs: _MockProcKwargs, make_album_search_item: pytest.FixtureRequest, is_lfm_rec: bool
    ) -> None:
        """A failed artist request is logged and treated as an empty listing, which becomes a no-match."""

        def _raise(*args: Any, **kwargs: Any) -> None:
            raise Exception("Fake exception intentionally raised.")

        mock_process_kwargs["state"].get_cached_artist_release_groups.return_value = None  # cache miss
        mock_process_kwargs["red"].get_artist_release_groups.side_effect = _raise
        mock_process_kwargs["state"].match_album_release.return_value = TorrentMatch(
            torrent_entry=None, above_max_size_found=False
        )
        mock_si = make_album_search_item(is_lfm_rec=is_lfm_rec)
        actual = SearchRedReleaseByPrefsModifier.process(si=mock_si, **mock_process_kwargs)
        mock_process_kwargs["state"].match_album_release.assert_called_once_with(si=mock_si, release_entries=[])
        # A failed fetch is NOT cached: a later rec by the same artist retries the request instead of inheriting
        # a silent no-match for the rest of the run.
        mock_process_kwargs["state"].cache_artist_release_groups.assert_not_called()
        assert actual is mock_si
        assert actual.torrent_entry is None
        assert actual.above_max_size_te_found is False
        assert actual.trace == [
            TraceStep(
                stage=SearchStage.RED_ARTIST,
                outcome=SearchStepOutcome.WARNING,
                detail='RED artist request failed for artist "artist"',
            )
        ]

    @pytest.mark.parametrize("is_lfm_rec", [False, True])
    def test_track_item_matches_via_origin_candidates(
        self, mock_process_kwargs: _MockProcKwargs, make_track_search_item: pytest.FixtureRequest, is_lfm_rec: bool
    ) -> None:
        """A track item is matched candidate-by-candidate; the matching candidate is persisted as the resolved origin."""
        mock_si = make_track_search_item(is_lfm_rec=is_lfm_rec)
        mock_si.search_id = 3
        candidates = [_origin("Album"), _origin("Single", primary_type="Single")]
        mock_si.set_origin_candidates(candidates)
        matched_te = TorrentEntry(
            torrent_id=1, media="WEB", format="FLAC", encoding="24bit Lossless", **_MOCK_TE_KWARGS
        )
        release_entries = [MagicMock(spec=ReleaseEntry)]

        def _match(si: SearchItem, release_entries: list[ReleaseEntry]) -> TorrentMatch:
            si.set_matched_origin(candidates[1])
            return TorrentMatch(torrent_entry=matched_te, above_max_size_found=False)

        mock_process_kwargs["state"].get_cached_artist_release_groups.return_value = release_entries
        mock_process_kwargs["state"].match_track_origin_candidates.side_effect = _match
        with patch(_UPSERT_RESOLVED_ORIGIN) as mock_upsert:
            actual = SearchRedReleaseByPrefsModifier.process(si=mock_si, **mock_process_kwargs)
        mock_process_kwargs["state"].match_track_origin_candidates.assert_called_once_with(
            si=mock_si, release_entries=release_entries
        )
        mock_process_kwargs["state"].get_candidate_release_groups.assert_not_called()
        assert actual.torrent_entry is matched_te and actual.release_name == "Single"
        mock_upsert.assert_called_once_with(
            search_id=3, origin=candidates[1], candidate_rank=1, candidate_count=2, matched=True
        )

    def test_track_item_without_match_persists_nothing(
        self, mock_process_kwargs: _MockProcKwargs, make_track_search_item: pytest.FixtureRequest
    ) -> None:
        mock_si = make_track_search_item(is_lfm_rec=True)
        mock_si.set_origin_candidates([_origin("Album")])
        mock_process_kwargs["state"].get_cached_artist_release_groups.return_value = []
        mock_process_kwargs["state"].match_track_origin_candidates.return_value = TorrentMatch(
            torrent_entry=None, above_max_size_found=True
        )
        with patch(_UPSERT_RESOLVED_ORIGIN) as mock_upsert:
            actual = SearchRedReleaseByPrefsModifier.process(si=mock_si, **mock_process_kwargs)
        mock_upsert.assert_not_called()
        assert actual.torrent_entry is None and actual.above_max_size_te_found is True
