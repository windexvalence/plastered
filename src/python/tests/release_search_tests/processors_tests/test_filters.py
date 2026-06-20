from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from plastered.db.db_models import SkipReason, Status
from plastered.models import EntityType
from plastered.models.search_item import SearchItem
from plastered.release_search.processors.filters import (
    BaseFilter,
    PreMBIDResolutionFilter,
    PostResolveOriginTrackFilter,
    PostMBIDResolutionFilter,
    PostRedSearchFilter,
)
from plastered.release_search.processors.bases import FilterFuncs
from plastered.release_search.search_helpers import SearchState


@pytest.mark.parametrize("processable", [False, True])
@pytest.mark.parametrize("entity_type", [et for et in EntityType])
@pytest.mark.parametrize(
    "filter_class",
    [PreMBIDResolutionFilter, PostResolveOriginTrackFilter, PostMBIDResolutionFilter, PostRedSearchFilter],
)
def test_filter_process(
    make_album_search_item: pytest.FixtureRequest,
    make_track_search_item: pytest.FixtureRequest,
    processable: bool,
    entity_type: EntityType,
    filter_class: BaseFilter,
) -> None:
    """Ensures calls to the given `BaseFilter` subclass' `process` method works as intended."""
    if filter_class == PostResolveOriginTrackFilter and entity_type == EntityType.ALBUM:
        pytest.skip(f"{PostResolveOriginTrackFilter.__class__.__qualname__} not relevant for albums.")

    mock_si = (
        make_album_search_item(is_lfm_rec=True)
        if entity_type == EntityType.ALBUM
        else make_track_search_item(is_lfm_rec=True)
    )
    mock_skip_reason = SkipReason.NO_MATCH_FOUND
    func_ret_val = None if processable else mock_skip_reason
    mock_filter_funcs: FilterFuncs = tuple([lambda si, state: func_ret_val for _ in range(len(filter_class.funcs))])
    with (
        patch.object(filter_class, "funcs", new_callable=PropertyMock) as mock_funcs_property,
        patch.object(filter_class, "_add_skipped_snatch", return_value=None) as mock_add_skipped_snatch,
    ):
        mock_funcs_property.return_value = mock_filter_funcs
        actual = filter_class.process(si=mock_si, state=MagicMock(spec=SearchState))
        if processable:
            assert isinstance(actual, SearchItem)
            (
                mock_add_skipped_snatch.assert_not_called(),
                f"Processable SearchItems should not lead to skip record creation.",
            )
        else:
            assert actual is None
            mock_add_skipped_snatch.assert_called_once_with(si=mock_si, skip_reason=mock_skip_reason)


@pytest.mark.parametrize("is_lfm_rec", [False, True])
@pytest.mark.parametrize("entity_type", [et for et in EntityType])
@pytest.mark.parametrize("skip_reason", [sr for sr in SkipReason])
def test_base_filter_add_skipped_snatch(
    make_track_search_item: pytest.FixtureRequest,
    make_album_search_item: pytest.FixtureRequest,
    is_lfm_rec: bool,
    entity_type: EntityType,
    skip_reason: SkipReason,
) -> None:
    mock_si = (
        make_album_search_item(is_lfm_rec=is_lfm_rec)
        if entity_type == EntityType.ALBUM
        else make_track_search_item(is_lfm_rec=is_lfm_rec)
    )
    with patch("plastered.release_search.processors.filters.set_result_status") as mock_set_result_status:
        BaseFilter._add_skipped_snatch(si=mock_si, skip_reason=skip_reason)
        mock_set_result_status.assert_called_once_with(
            search_id=mock_si.search_id, status=Status.SKIPPED, status_model_kwargs={"skip_reason": skip_reason}
        )
