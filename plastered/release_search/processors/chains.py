from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from plastered.models import EntityType
from plastered.release_search.processors.filters import (
    PostMBIDResolutionFilter,
    PostRedSearchFilter,
    PostResolveOriginTrackFilter,
    PreMBIDResolutionFilter,
)
from plastered.release_search.processors.modifiers import (
    AttachSearchIdModifier,
    AttemptResolveMBReleaseModifier,
    ResolveAlbumInfoModifier,
    ResolveTrackInfoModifier,
    SearchRedReleaseByPrefsModifier,
)

if TYPE_CHECKING:
    from plastered.models import SearchItem
    from plastered.release_search.processors.bases import SearchItemProcessor
    from plastered.release_search.search_helpers import SearchState
    from plastered.utils.httpx_utils import LFMAPIClient, MusicBrainzAPIClient, RedAPIClient


_LOGGER = logging.getLogger(__name__)


@dataclass
class SearchItemProcessorChain:
    """
    Maintains the order of operations for processing a `SearchItem`. Applies the `SearchItemProcessors` to the provided
    `SearchItem` instance(s) and returns the results.
    """

    lfm: LFMAPIClient
    mb: MusicBrainzAPIClient
    red: RedAPIClient
    search_state: SearchState
    album_chain: tuple[type[SearchItemProcessor], ...] = tuple(
        [
            AttachSearchIdModifier,
            PreMBIDResolutionFilter,
            ResolveAlbumInfoModifier,
            AttemptResolveMBReleaseModifier,
            PostMBIDResolutionFilter,
            SearchRedReleaseByPrefsModifier,
            PostRedSearchFilter,
        ]
    )
    track_chain: tuple[type[SearchItemProcessor], ...] = tuple(
        [
            ResolveTrackInfoModifier,
            PostResolveOriginTrackFilter,
            AttachSearchIdModifier,  # TODO: should the track chain also start with search record creation?
            PreMBIDResolutionFilter,
            AttemptResolveMBReleaseModifier,
            PostMBIDResolutionFilter,
            SearchRedReleaseByPrefsModifier,
            PostRedSearchFilter,
        ]
    )

    def batch_process(self, entity_to_si_list: dict[EntityType, list[SearchItem]]) -> list[SearchItem]:
        """Processes the list of `SearchItems` and returns the resulting list of processed `SearchItems`."""
        entity_chains = {EntityType.ALBUM: self.album_chain, EntityType.TRACK: self.track_chain}
        processed = [
            self._apply_chain(si=si, chain=chain)
            for entity_type, chain in entity_chains.items()
            for si in entity_to_si_list.get(entity_type, [])
        ]
        return [si for si in processed if si is not None]

    def _apply_chain(self, si: SearchItem, chain: tuple[type[SearchItemProcessor], ...]) -> SearchItem | None:
        for processor in chain:
            if not processor.process(si=si, state=self.search_state, lfm=self.lfm, mb=self.mb, red=self.red):
                _LOGGER.debug(f"si for {si.initial_info} filtered by: {processor.__class__.__name__}")
                return None
        return si
