from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from plastered.db.db_models import SkipReason
    from plastered.models import SearchItem
    from plastered.release_search.search_helpers import SearchState
    from plastered.utils.httpx_utils import LFMAPIClient, MusicBrainzAPIClient, RedAPIClient


class SearchItemModifier(ABC):
    """
    Protocol for functions invoked on search items to modify their inputs, as part of the release searcher call stack.

    Returns: the modified `SearchItem`.
    """

    @staticmethod
    @abstractmethod
    def process(
        si: SearchItem, state: SearchState, lfm: LFMAPIClient, mb: MusicBrainzAPIClient, red: RedAPIClient
    ) -> SearchItem: ...


# Type defs for reduced boilerplate
type FilterFuncs = tuple[Callable[[SearchItem, SearchState], SkipReason | None], ...]


class SearchItemFilter(ABC):
    """
    Required interface for any callable class which takes in a SearchItem and returns a boolean as part of the
    ReleaseSearcher's call stack.

    Returns: `True` when the given `SearchItem` is still valid for processing, otherwise
        returns `False` when the given `SearchItem` should be dropped due to not meeting the filter's criteria.
    """

    funcs: ClassVar[FilterFuncs]

    @classmethod
    @abstractmethod
    def process(cls, si: SearchItem, state: SearchState, **kwargs: Any) -> SearchItem | None: ...


type SearchItemProcessor = SearchItemModifier | SearchItemFilter
