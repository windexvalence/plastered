"""Implementations of the `SearchItemFilter` abstract base class should live in this file."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from plastered.db.db_models import SkipReason, Status
from plastered.db.db_utils import set_result_status
from plastered.release_search.processors.bases import SearchItemFilter

if TYPE_CHECKING:
    from plastered.models import SearchItem
    from plastered.release_search.processors.bases import FilterFuncs
    from plastered.release_search.search_helpers import SearchState

_LOGGER = logging.getLogger(__name__)


class BaseFilter(SearchItemFilter):
    """Base class for all `SearchItemFilter` implementations."""

    @classmethod
    def process(cls, si: SearchItem, state: SearchState, **kwargs: Any) -> SearchItem | None:
        for func in cls.funcs:
            if skip_reason := func(si, state):
                cls._add_skipped_snatch(si=si, skip_reason=skip_reason)
                return None
        _LOGGER.debug(f"{si.initial_info} passed all {cls.__name__} filters.")
        return si

    @classmethod
    def _add_skipped_snatch(cls, si: SearchItem, skip_reason: SkipReason) -> None:
        """Adds a Skipped db record for the given `SearchItem` and `SkipReason`."""
        _LOGGER.debug(f"{si.initial_info} filtered by {cls.__name__} for reason {skip_reason.name}.")
        set_result_status(
            search_id=si.search_id, status=Status.SKIPPED, status_model_kwargs={"skip_reason": skip_reason}
        )


class PreMBIDResolutionFilter(BaseFilter):
    """Intended as a replacement for `SearchState.pre_mbid_resolution_filter`."""

    funcs: ClassVar[FilterFuncs] = tuple(
        [
            lambda si, state: state._pre_mbid_reso_rule_not_previously_snatched(si=si),
            lambda si, state: state._pre_mbid_reso_rule_allowed_rec_context(si=si),
        ]
    )


class PostResolveOriginTrackFilter(BaseFilter):
    """Intended as a replacement for `SearchState.post_resolve_track_filter`."""

    funcs: ClassVar[FilterFuncs] = tuple(
        [lambda si, _: None if si._lfm_track_info else SkipReason.NO_SOURCE_RELEASE_FOUND]
    )


class PostMBIDResolutionFilter(BaseFilter):
    """Intended as a replacement for `SearchState.post_mbid_resolution_filter`."""

    funcs: ClassVar[FilterFuncs] = tuple([lambda si, state: state.post_mbid_reso_rule_has_required_fields(si=si)])


class PostRedSearchFilter(BaseFilter):
    """Intended as a replacement for `SearchState.post_red_search_filter`."""

    funcs: ClassVar[FilterFuncs] = tuple(
        [
            lambda si, state: state.post_red_search_rule_found_match_with_allowed_size(si=si),
            lambda si, state: state._post_red_search_rule_not_dupe_snatch(si=si),
            lambda si, state: state.add_search_item_to_snatch(si=si),
        ]
    )
