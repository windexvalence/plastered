from __future__ import annotations

import logging
from collections.abc import Callable
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
            # Create the SearchRecord first (as in album_chain) so any subsequent filter that drops the item has a
            # search_id to attach the SKIPPED/FAILED row to. Otherwise a track that fails origin-release resolution
            # would hit PostResolveOriginTrackFilter with search_id=None and crash the whole run via set_result_status.
            AttachSearchIdModifier,
            ResolveTrackInfoModifier,
            PostResolveOriginTrackFilter,
            PreMBIDResolutionFilter,
            AttemptResolveMBReleaseModifier,
            PostMBIDResolutionFilter,
            SearchRedReleaseByPrefsModifier,
            PostRedSearchFilter,
        ]
    )

    def batch_process(
        self,
        entity_to_si_list: dict[EntityType, list[SearchItem]],
        progress_callback: Callable[[], None] | None = None,
    ) -> list[SearchItem]:
        """
        Processes the list of `SearchItems` and returns the resulting list of processed `SearchItems`. `progress_callback`,
        if provided, is invoked once per item processed (used by the scraper run UI to report progress).
        """
        entity_chains = {EntityType.ALBUM: self.album_chain, EntityType.TRACK: self.track_chain}
        processed: list[SearchItem] = []
        for entity_type, chain in entity_chains.items():
            for si in entity_to_si_list.get(entity_type, []):
                result = self._apply_chain(si=si, chain=chain)
                if progress_callback is not None:
                    progress_callback()
                if result is not None:
                    processed.append(result)
        return processed

    def _apply_chain(self, si: SearchItem, chain: tuple[type[SearchItemProcessor], ...]) -> SearchItem | None:
        for processor in chain:
            if not processor.process(si=si, state=self.search_state, lfm=self.lfm, mb=self.mb, red=self.red):
                _LOGGER.debug(f"si for {si.initial_info} filtered by: {processor.__name__}")
                return None
        return si
