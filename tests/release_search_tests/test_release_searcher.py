from typing import Generator, NamedTuple
from unittest.mock import MagicMock, patch

import pytest

from plastered.config.app_settings import AppSettings, RedSearchOverrides
from plastered.models import (
    AdhocSearch,
    EntityType as et,
    LFMRec,
    LFMTrackInfo,
    MBRelease,
    RecContext as rc,
    SearchItem,
    TorrentEntry as te,
)
from plastered.release_search.processors import SearchItemProcessorChain
from plastered.release_search.release_searcher import ReleaseSearcher, _dedupe_recs
from plastered.release_search.search_helpers import SearchState
from plastered.run_cache.run_cache import RunCache
from plastered.snatch import Snatcher
from plastered.utils.httpx_utils import LFMAPIClient, MusicBrainzAPIClient, RedAPIClient, RedSnatchAPIClient


@pytest.fixture(scope="function")
def mock_lfm_track_info() -> LFMTrackInfo:
    return LFMTrackInfo("Some Artist", "Track Title", "Source Album", "https://fake-url", "69-420")


@pytest.fixture(scope="function")
def initial_search_state(valid_app_settings: AppSettings) -> SearchState:
    return SearchState(app_settings=valid_app_settings)


@pytest.fixture(scope="function")
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


@pytest.fixture(scope="function")
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


@pytest.fixture(scope="function")
def mock_run_cache() -> Generator[None, None, None]:
    mock_rc = MagicMock(spec=RunCache)
    with patch("plastered.release_search.release_searcher.RunCache") as mock_rc_new:
        mock_rc = mock_rc_new.return_value
        yield mock_rc


class _MockRsKwargs(NamedTuple):
    """Collection of ReleaseSearcher mock instance attr classes which are expensive to generate."""

    app_settings: AppSettings
    red_api_client: MagicMock
    red_snatch_client: MagicMock
    lfm_client: MagicMock
    musicbrainz_client: MagicMock


@pytest.fixture(scope="function")
def mock_kwargs(valid_app_settings: AppSettings, mock_run_cache: MagicMock) -> _MockRsKwargs:
    """Fixture for mocking the ReleaseSeacher instance attr classes which are expensive to generate."""
    return _MockRsKwargs(
        app_settings=valid_app_settings,
        red_api_client=MagicMock(spec=RedAPIClient),
        red_snatch_client=MagicMock(spec=RedSnatchAPIClient),
        lfm_client=MagicMock(spec=LFMAPIClient),
        musicbrainz_client=MagicMock(spec=MusicBrainzAPIClient),
    )


@pytest.mark.parametrize(
    "ent_to_recs",
    [
        {},
        {et.ALBUM: []},
        {et.TRACK: []},
        {et.ALBUM: [LFMRec("artist1", "ent1", et.ALBUM, rc.IN_LIBRARY)]},
        {et.TRACK: [LFMRec("artist2", "ent2", et.TRACK, rc.IN_LIBRARY)]},
        {
            et.ALBUM: [LFMRec("artist3", "ent3", et.ALBUM, rc.IN_LIBRARY)],
            et.TRACK: [LFMRec("artist4", "ent4", et.TRACK, rc.IN_LIBRARY)],
        },
        {et.ALBUM: [LFMRec("a", "e", et.ALBUM, rc.IN_LIBRARY), LFMRec("a2", "e2", et.ALBUM, rc.IN_LIBRARY)]},
        {et.TRACK: [LFMRec("a", "e", et.TRACK, rc.IN_LIBRARY), LFMRec("a2", "e2", et.TRACK, rc.IN_LIBRARY)]},
    ],
)
def test_search_for_recs(mock_kwargs: _MockRsKwargs, ent_to_recs: dict[et, list[LFMRec]]) -> None:
    with ReleaseSearcher(**mock_kwargs._asdict()) as rs:
        with (
            patch.object(rs, "_apply_si_processor_chain") as mock_apply_si_processor_chain_method,
            patch.object(Snatcher, "snatch_matches") as mock_snatch_matches_method,
        ):
            rs.search_for_recs(entity_to_recs_list=ent_to_recs)
            mock_apply_si_processor_chain_method.assert_called_once()
            mock_snatch_matches_method.assert_called_once()


def test_search_for_recs_with_snatch_override_and_progress_callback(mock_kwargs: _MockRsKwargs) -> None:
    """search_for_recs honors a snatch override and threads the progress callback to the processor chain."""

    def _callback() -> None:
        return None

    with ReleaseSearcher(**mock_kwargs._asdict()) as rs:
        with (
            patch.object(rs, "_apply_si_processor_chain") as mock_apply,
            patch.object(Snatcher, "snatch_matches") as mock_snatch,
        ):
            rs.search_for_recs(
                {et.ALBUM: [LFMRec("a", "e", et.ALBUM, rc.IN_LIBRARY)]},
                snatch_override=True,
                progress_callback=_callback,
            )
            mock_apply.assert_called_once()
            assert mock_apply.call_args.kwargs["progress_callback"] is _callback
            mock_snatch.assert_called_once()


def test_dedupe_recs_preserves_order_and_drops_dupes() -> None:
    """`_dedupe_recs` drops recs equal by `LFMRec.__eq__` while preserving first-seen order."""
    r1 = LFMRec("a", "e", et.ALBUM, rc.IN_LIBRARY)
    r2 = LFMRec("a", "e", et.ALBUM, rc.IN_LIBRARY)  # duplicate of r1
    r3 = LFMRec("a", "e", et.TRACK, rc.IN_LIBRARY)  # distinct: track vs album
    r4 = LFMRec("b", "e", et.ALBUM, rc.IN_LIBRARY)  # distinct artist
    deduped = _dedupe_recs([r1, r2, r3, r4])
    assert deduped == [r1, r3, r4]


def test_search_for_recs_dedupes_identical_recs(mock_kwargs: _MockRsKwargs) -> None:
    """Duplicate recs mapping to the same release are collapsed before the processor chain runs."""
    recs = [
        LFMRec("a", "e", et.ALBUM, rc.IN_LIBRARY),
        LFMRec("a", "e", et.ALBUM, rc.IN_LIBRARY),  # duplicate
        LFMRec("b", "e2", et.ALBUM, rc.IN_LIBRARY),
    ]
    with ReleaseSearcher(**mock_kwargs._asdict()) as rs:
        with patch.object(rs, "_apply_si_processor_chain") as mock_apply, patch.object(Snatcher, "snatch_matches"):
            rs.search_for_recs(entity_to_recs_list={et.ALBUM: recs})
        si_list = mock_apply.call_args.kwargs["entity_to_si_list"][et.ALBUM]
    assert len(si_list) == 2


@pytest.mark.parametrize("snatch_enabled", [True, False])
@pytest.mark.parametrize(
    "adhoc_search",
    [AdhocSearch(artist="Some Artist", release="Some Album"), AdhocSearch(artist="Some Artist", track="Some Track")],
)
def test_adhoc_search(mock_kwargs: _MockRsKwargs, adhoc_search: AdhocSearch, snatch_enabled: bool) -> None:
    """
    Ensures the ad-hoc flow runs the item through the chain, then snatches when snatching is enabled, or records the
    matched release (search-only) when it is not.
    """
    overrides = RedSearchOverrides(snatch=snatch_enabled)
    with ReleaseSearcher(**mock_kwargs._asdict()) as rs:
        with (
            patch.object(rs, "_apply_si_processor_chain") as mock_apply_si_processor_chain_method,
            patch.object(Snatcher, "snatch_matches") as mock_snatch_matches_method,
            patch.object(SearchState, "record_matched_result_row") as mock_record_matched_method,
        ):
            rs.adhoc_search(adhoc_search=adhoc_search, search_id=69, overrides=overrides)
            mock_apply_si_processor_chain_method.assert_called_once()
            if snatch_enabled:
                mock_snatch_matches_method.assert_called_once_with(manual_run=True)
                mock_record_matched_method.assert_not_called()
            else:
                mock_record_matched_method.assert_called_once_with()
                mock_snatch_matches_method.assert_not_called()


@pytest.mark.parametrize("snatch_raises", [False, True])
def test_snatch_recorded_match(mock_kwargs: _MockRsKwargs, snatch_raises: bool) -> None:
    """Per-result Download: snatches the recorded tid and writes GRABBED on success or FAILED on error."""
    from plastered.db.db_models import FailReason, Matched, Status

    matched = Matched(
        m_result_id=69,
        tid=420,
        red_permalink="https://red/x",
        matched_mbid="mbid",
        size_gb=1.0,
        media="CD",
        format="FLAC",
        encoding="Lossless",
    )
    with ReleaseSearcher(**mock_kwargs._asdict()) as rs:
        rs._red_snatch_client.tid_snatched_with_fl_token.return_value = False
        if snatch_raises:
            rs._red_snatch_client.snatch.side_effect = OSError("boom")
        else:
            rs._red_snatch_client.snatch.return_value = b"torrent-bytes"
        with (
            patch("plastered.release_search.release_searcher.set_result_status") as mock_set_status,
            patch("plastered.release_search.release_searcher.Path.write_bytes") as mock_write_bytes,
            # On failure, simulate a partial .torrent artifact so the cleanup (os.remove) branch is exercised.
            patch("plastered.release_search.release_searcher.os.path.exists", return_value=snatch_raises),
            patch("plastered.release_search.release_searcher.os.remove") as mock_remove,
        ):
            rs.snatch_recorded_match(search_id=69, matched=matched)

        rs._red_snatch_client.snatch.assert_called_once_with(tid="420", can_use_token=False)
        mock_set_status.assert_called_once()
        status_kwarg = mock_set_status.call_args.kwargs["status"]
        model_kwargs = mock_set_status.call_args.kwargs["status_model_kwargs"]
        if snatch_raises:
            assert status_kwarg == Status.FAILED
            assert model_kwargs["fail_reason"] == FailReason.FILE_ERROR
            mock_write_bytes.assert_not_called()
            mock_remove.assert_called_once()
        else:
            assert status_kwarg == Status.GRABBED
            assert model_kwargs["tid"] == 420
            mock_write_bytes.assert_called_once_with(b"torrent-bytes")


@pytest.mark.parametrize(
    "ent_to_cnt",
    [
        {et.ALBUM: 0, et.TRACK: 0},
        {et.ALBUM: 1, et.TRACK: 0},
        {et.ALBUM: 0, et.TRACK: 1},
        {et.ALBUM: 1, et.TRACK: 1},
        {et.ALBUM: 2, et.TRACK: 2},
    ],
)
def test_apply_si_processor_chain(
    mock_kwargs: _MockRsKwargs, initial_search_state: SearchState, ent_to_cnt: dict[et, int]
) -> None:
    n_alb, n_track = ent_to_cnt.get(et.ALBUM, 0), ent_to_cnt.get(et.TRACK, 0)
    ent_to_sis = {
        et.ALBUM: [SearchItem(initial_info=LFMRec("artist", "ent", et.ALBUM, rc.IN_LIBRARY)) for _ in range(n_alb)],
        et.TRACK: [SearchItem(initial_info=LFMRec("artist", "ent", et.ALBUM, rc.IN_LIBRARY)) for _ in range(n_track)],
    }
    mock_processed = []
    for si_list in ent_to_sis.values():
        mock_processed.extend([si_list])
    with ReleaseSearcher(**mock_kwargs._asdict()) as rs:
        with patch.object(SearchItemProcessorChain, "batch_process", return_value=mock_processed):
            actual = rs._apply_si_processor_chain(entity_to_si_list=ent_to_sis, search_state=initial_search_state)
            assert actual == mock_processed


def test_exit_closes_owned_run_cache(valid_app_settings: AppSettings, mock_run_cache: MagicMock) -> None:
    """When ReleaseSearcher builds its own clients it owns the RunCache and closes it on __exit__."""
    with ReleaseSearcher(app_settings=valid_app_settings) as rs:
        assert rs._run_cache is mock_run_cache
    mock_run_cache.close.assert_called_once()
