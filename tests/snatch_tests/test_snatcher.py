from collections.abc import Callable, Generator
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest

from plastered.models import EntityType as et, LFMRec, RecContext as rc, SearchItem, TorrentEntry as te
from plastered.release_search.search_helpers import SearchState
from plastered.snatch import Snatcher
from plastered.utils.httpx_utils import RedSnatchAPIClient

SnatcherFactory = Callable[..., tuple[Snatcher, MagicMock, MagicMock]]


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
def fake_snatch_dir(tmp_path: Path) -> Path:
    tmp_snatch_dir = tmp_path / "snatches"
    tmp_snatch_dir.mkdir()
    return tmp_snatch_dir


@pytest.fixture(scope="function")
def make_snatcher() -> Generator[SnatcherFactory, None, None]:
    """
    Factory fixture (https://docs.pytest.org/en/stable/how-to/fixtures.html#factories-as-fixtures) returning a builder
    for `(Snatcher, mock_red_snatch_client, mock_search_state)` tuples. The dependency mocks are created via `patch`
    context managers so their lifecycle is cleaned up automatically once the consuming test completes.
    """
    with (
        patch("plastered.utils.httpx_utils.RedSnatchAPIClient", spec=RedSnatchAPIClient) as mock_red_snatch_client,
        patch("plastered.release_search.search_helpers.SearchState", spec=SearchState) as mock_search_state,
    ):

        def _make_snatcher(snatch_directory: Path, enable_snatches: bool) -> tuple[Snatcher, MagicMock, MagicMock]:
            snatcher = Snatcher(
                red_snatch_client=mock_red_snatch_client,
                search_state=mock_search_state,
                snatch_directory=snatch_directory,
                enable_snatches=enable_snatches,
            )
            return snatcher, mock_red_snatch_client, mock_search_state

        yield _make_snatcher


@pytest.mark.parametrize("manual_run", [False, True])
@pytest.mark.parametrize("ent_type", [m for m in et])
@pytest.mark.parametrize("enable_snatches", [False, True])
def test_snatch_matches(
    make_snatcher: SnatcherFactory, fake_snatch_dir: Path, manual_run: bool, ent_type: et, enable_snatches: bool
) -> None:
    expect_calls = enable_snatches
    mock_si_to_snatch = SearchItem(initial_info=LFMRec("artist", "ent", ent_type, rc.IN_LIBRARY))
    snatcher, _, mock_search_state = make_snatcher(snatch_directory=fake_snatch_dir, enable_snatches=enable_snatches)
    mock_search_state.get_search_items_to_snatch.return_value = [mock_si_to_snatch]
    with patch.object(Snatcher, "_snatch_match") as mock_snatch_match_method:
        snatcher.snatch_matches(manual_run=manual_run)
        if expect_calls:
            mock_search_state.get_search_items_to_snatch.assert_called_once_with(manual_run=manual_run)
            mock_snatch_match_method.assert_called_once_with(si_to_snatch=mock_si_to_snatch)
        else:
            mock_search_state.get_search_items_to_snatch.assert_not_called()
            mock_snatch_match_method.assert_not_called()


@pytest.mark.parametrize("ent_type", [m for m in et])
@pytest.mark.parametrize("rec_ctx", [r for r in rc])
@pytest.mark.parametrize("used_fl_token", [False, True])
def test_snatch_match_valid(
    make_snatcher: SnatcherFactory,
    mock_best_te: te,
    fake_snatch_dir: Path,
    ent_type: et,
    rec_ctx: rc,
    used_fl_token: bool,
) -> None:
    mock_tid = mock_best_te.torrent_id
    expected_out_filepath = fake_snatch_dir / f"{mock_tid}.torrent"
    mock_content_bytes = b"some-fake-bytes"
    si_to_snatch = SearchItem(initial_info=LFMRec("artist", "ent", ent_type, rec_ctx), torrent_entry=mock_best_te)
    snatcher, mock_red_snatch_client, mock_search_state = make_snatcher(
        snatch_directory=fake_snatch_dir, enable_snatches=True
    )
    mock_red_snatch_client.snatch.return_value = mock_content_bytes
    mock_red_snatch_client.tid_snatched_with_fl_token.return_value = used_fl_token
    snatcher._snatch_match(si_to_snatch=si_to_snatch)
    assert expected_out_filepath.exists()
    assert expected_out_filepath.read_bytes() == mock_content_bytes
    mock_red_snatch_client.snatch.assert_called_once_with(tid=str(mock_tid), can_use_token=ANY)
    mock_red_snatch_client.tid_snatched_with_fl_token.assert_called_once_with(tid=mock_tid)
    mock_search_state.add_snatch_final_status_row.assert_called_once()
