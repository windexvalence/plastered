from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from plastered.models import EntityType, SearchItem
from plastered.release_search.search_helpers import SearchState
from plastered.release_search.processors import SearchItemProcessorChain
from plastered.release_search.processors.bases import SearchItemProcessor
from plastered.utils.httpx_utils import LFMAPIClient, MusicBrainzAPIClient, RedAPIClient


# Function-scoped: each test gets a fresh chain so no test can leak mutated state (e.g. a patched
# album_chain/track_chain) into another.
@pytest.fixture(scope="function")
def chain_instance() -> SearchItemProcessorChain:
    mock_lfm_client = MagicMock(spec=LFMAPIClient)
    mock_mb_client = MagicMock(spec=MusicBrainzAPIClient)
    mock_red_client = MagicMock(spec=RedAPIClient)
    mock_search_state = MagicMock(spec=SearchState)
    return SearchItemProcessorChain(
        lfm=mock_lfm_client, mb=mock_mb_client, red=mock_red_client, search_state=mock_search_state
    )


@pytest.fixture(scope="function")
def create_mock_processor() -> Callable[[bool], MagicMock]:
    """
    Fixture factory to generate Mock `SearchItemProcessor` instances on the fly.
    https://docs.pytest.org/en/stable/how-to/fixtures.html#factories-as-fixtures
    """

    def _create_mock_processor(processable: bool) -> MagicMock:
        def _side_effect(**kwargs: Any) -> bool:
            return kwargs.get("si") if processable else None

        # Real processors are classes, so the chain reads `processor.__name__` for skip logging; give the mock one.
        mock_proc = MagicMock(__name__="MockProcessor")
        mock_proc.process.side_effect = _side_effect
        return mock_proc

    return _create_mock_processor


@pytest.mark.parametrize("num_input_albums, num_input_tracks", [(0, 0), (0, 1), (1, 0), (1, 1), (2, 2)])
def test_batch_process(
    make_album_search_item: pytest.FixtureRequest,
    make_track_search_item: pytest.FixtureRequest,
    chain_instance: SearchItemProcessorChain,
    num_input_albums: int,
    num_input_tracks: int,
) -> None:
    with patch.object(chain_instance, "_apply_chain", return_value=[]) as mock_apply_chain:
        mock_input_dict = {
            EntityType.ALBUM: [make_album_search_item(is_lfm_rec=True) for _ in range(num_input_albums)],
            EntityType.TRACK: [make_track_search_item(is_lfm_rec=True) for _ in range(num_input_tracks)],
        }
        actual = chain_instance.batch_process(entity_to_si_list=mock_input_dict)
        assert len(actual) == num_input_albums + num_input_tracks
        assert len(mock_apply_chain.call_args_list) == num_input_albums + num_input_tracks
        album_chain_calls = sum(
            1 for call in mock_apply_chain.call_args_list if call.kwargs["chain"] == chain_instance.album_chain
        )
        track_chain_calls = sum(
            1 for call in mock_apply_chain.call_args_list if call.kwargs["chain"] == chain_instance.track_chain
        )
        assert album_chain_calls == num_input_albums
        assert track_chain_calls == num_input_tracks


@pytest.mark.parametrize("entity_type", [et for et in EntityType])
def test_apply_chain_all_processable(
    chain_instance: SearchItemProcessorChain,
    create_mock_processor: pytest.FixtureRequest,
    make_album_search_item: pytest.FixtureRequest,
    make_track_search_item: pytest.FixtureRequest,
    entity_type: EntityType,
) -> None:
    """Ensures SearchItemProcessorChain._apply_chain works as intended when all processors return non-None."""
    mock_si = (
        make_album_search_item(is_lfm_rec=True)
        if entity_type == EntityType.ALBUM
        else make_track_search_item(is_lfm_rec=True)
    )
    real_chain = chain_instance.album_chain if entity_type == EntityType.ALBUM else chain_instance.track_chain
    # `_apply_chain` takes the chain as an argument, so pass a mock chain directly rather than patching the instance.
    mock_chain = tuple(create_mock_processor(True) for _ in range(len(real_chain)))
    actual = chain_instance._apply_chain(si=mock_si, chain=mock_chain)
    assert actual is mock_si
    for mock_processor in mock_chain:
        mock_processor.process.assert_called_once_with(
            si=mock_si,
            state=chain_instance.search_state,
            lfm=chain_instance.lfm,
            mb=chain_instance.mb,
            red=chain_instance.red,
        )


@pytest.mark.parametrize("entity_type", [et for et in EntityType])
def test_apply_chain_not_processable(
    chain_instance: SearchItemProcessorChain,
    create_mock_processor: pytest.FixtureRequest,
    make_album_search_item: pytest.FixtureRequest,
    make_track_search_item: pytest.FixtureRequest,
    entity_type: EntityType,
) -> None:
    """Ensures SearchItemProcessorChain._apply_chain works as intended when any processor returns `None`."""
    mock_si = (
        make_album_search_item(is_lfm_rec=True)
        if entity_type == EntityType.ALBUM
        else make_track_search_item(is_lfm_rec=True)
    )
    real_chain = chain_instance.album_chain if entity_type == EntityType.ALBUM else chain_instance.track_chain
    # `_apply_chain` takes the chain as an argument, so pass a mock chain directly rather than patching the instance.
    mock_chain = tuple(create_mock_processor(False) for _ in range(len(real_chain)))
    actual = chain_instance._apply_chain(si=mock_si, chain=mock_chain)
    assert actual is None
    # The first processor returns None, short-circuiting the chain; none after it should be invoked.
    mock_chain[0].process.assert_called_once_with(
        si=mock_si,
        state=chain_instance.search_state,
        lfm=chain_instance.lfm,
        mb=chain_instance.mb,
        red=chain_instance.red,
    )
    for mock_processor in mock_chain[1:]:
        mock_processor.process.assert_not_called()


def test_track_chain_creates_search_record_before_filtering(chain_instance: SearchItemProcessorChain) -> None:
    """
    Regression: AttachSearchIdModifier must run before PostResolveOriginTrackFilter in the track chain. Otherwise a
    track that fails origin-release resolution is dropped with search_id=None, crashing the run via set_result_status.
    """
    from plastered.release_search.processors.filters import PostResolveOriginTrackFilter
    from plastered.release_search.processors.modifiers import AttachSearchIdModifier

    track_chain = chain_instance.track_chain
    assert track_chain[0] is AttachSearchIdModifier
    assert track_chain.index(AttachSearchIdModifier) < track_chain.index(PostResolveOriginTrackFilter)
