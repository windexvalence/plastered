from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
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
        processed_albums = [self._apply_album_chain(si=si) for si in entity_to_si_list.get(EntityType.ALBUM, [])]
        processed_tracks = [self._apply_track_chain(si=si) for si in entity_to_si_list.get(EntityType.TRACK, [])]
        return [si for si in processed_albums + processed_tracks if si is not None]

    async def async_batch_process(self, search_items: list[SearchItem]) -> list[SearchItem]:  # pragma: no cover
        """Async equivalent of `batch_process`, but using the underlying `SearchItemProcessor` async methods."""
        partitioned_items = defaultdict(list)
        for si in search_items:
            partitioned_items[si.initial_info.entity_type].append(si)
        processed_albums = await asyncio.gather(  # type: ignore
            [self._async_apply_album_chain(si=si) for si in partitioned_items.get(EntityType.ALBUM, [])]
        )
        processed_tracks = await asyncio.gather(  # type: ignore
            [self._async_apply_track_chain(si=si) for si in partitioned_items.get(EntityType.TRACK, [])]
        )
        return [si for si in processed_albums + processed_tracks if si is not None]

    def _apply_album_chain(self, si: SearchItem) -> SearchItem | None:
        return self._apply_chain(si=si, chain=self.album_chain)

    async def _async_apply_album_chain(self, si: SearchItem) -> SearchItem | None:  # pragma: no cover
        res = await self._async_apply_chain(si=si, chain=self.album_chain)
        return res

    def _apply_track_chain(self, si: SearchItem) -> SearchItem | None:
        return self._apply_chain(si=si, chain=self.track_chain)

    async def _async_apply_track_chain(self, si: SearchItem) -> SearchItem | None:  # pragma: no cover
        res = await self._async_apply_chain(si=si, chain=self.track_chain)
        return res

    def _apply_chain(self, si: SearchItem, chain: tuple[type[SearchItemProcessor], ...]) -> SearchItem | None:
        for processor in chain:
            if not processor.process(si=si, state=self.search_state, lfm=self.lfm, mb=self.mb, red=self.red):
                _LOGGER.debug(f"si for {si.initial_info} filtered by: {processor.__class__.__name__}")
                return None
        return si

    async def _async_apply_chain(
        self, si: SearchItem, chain: tuple[type[SearchItemProcessor], ...]
    ) -> SearchItem | None:  # pragma: no cover
        for processor in chain:
            res = await processor.a_process(si=si, state=self.search_state, lfm=self.lfm, mb=self.mb, red=self.red)
            if not res:
                return None
        return si
