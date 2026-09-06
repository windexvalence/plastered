from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from plastered.db.db_models import SkipReason, Status
from plastered.models import EntityType, SearchStage, SearchStepOutcome, TraceStep
from plastered.models.search_item import SearchItem
from plastered.models import OriginRelease, OriginSource
from plastered.release_search.processors.filters import (
    BaseFilter,
    PreMBIDResolutionFilter,
    PostResolveOriginTrackFilter,
    PostMBIDResolutionFilter,
    PostRedSearchFilter,
    _origin_track_skip_reason,
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
        patch.object(filter_class, "_mark_skipped", return_value=None) as mock_mark_skipped,
    ):
        mock_funcs_property.return_value = mock_filter_funcs
        actual = filter_class.process(si=mock_si, state=MagicMock(spec=SearchState))
        if processable:
            assert isinstance(actual, SearchItem)
            (mock_mark_skipped.assert_not_called(), f"Processable SearchItems should not lead to skip record creation.")
        else:
            assert actual is None
            mock_mark_skipped.assert_called_once_with(si=mock_si, skip_reason=mock_skip_reason)


_FILTER_CLASSES = [PreMBIDResolutionFilter, PostResolveOriginTrackFilter, PostMBIDResolutionFilter, PostRedSearchFilter]


@pytest.mark.parametrize("is_lfm_rec", [False, True])
@pytest.mark.parametrize("entity_type", [et for et in EntityType])
@pytest.mark.parametrize("skip_reason", [sr for sr in SkipReason])
@pytest.mark.parametrize("filter_class", _FILTER_CLASSES)
def test_base_filter_mark_skipped(
    make_track_search_item: pytest.FixtureRequest,
    make_album_search_item: pytest.FixtureRequest,
    is_lfm_rec: bool,
    entity_type: EntityType,
    skip_reason: SkipReason,
    filter_class: type[BaseFilter],
) -> None:
    """The stop is traced under the filter's stage and persisted before the terminal status is written."""
    mock_si = (
        make_album_search_item(is_lfm_rec=is_lfm_rec)
        if entity_type == EntityType.ALBUM
        else make_track_search_item(is_lfm_rec=is_lfm_rec)
    )
    manager = MagicMock()
    with (
        patch("plastered.release_search.processors.filters.set_result_status") as mock_set_result_status,
        patch("plastered.release_search.processors.filters.persist_search_trace") as mock_persist_search_trace,
    ):
        manager.attach_mock(mock_set_result_status, "set_result_status")
        manager.attach_mock(mock_persist_search_trace, "persist_search_trace")
        filter_class._mark_skipped(si=mock_si, skip_reason=skip_reason)
    mock_set_result_status.assert_called_once_with(
        search_id=mock_si.search_id, status=Status.SKIPPED, status_model_kwargs={"skip_reason": skip_reason}
    )
    mock_persist_search_trace.assert_called_once_with(si=mock_si)
    assert [c[0] for c in manager.mock_calls] == ["persist_search_trace", "set_result_status"]
    assert mock_si.trace == [
        TraceStep(stage=filter_class.stage, outcome=SearchStepOutcome.STOPPED, detail=str(skip_reason))
    ]


def test_filter_stages() -> None:
    assert [filter_class.stage for filter_class in _FILTER_CLASSES] == [
        SearchStage.PRIOR_SNATCH,
        SearchStage.TRACK_ORIGIN,
        SearchStage.REQUIRED_FIELDS,
        SearchStage.RED_MATCH,
    ]


@pytest.mark.parametrize(
    "has_track_info, lfm_request_failed, mb_request_failed, expected",
    [
        (True, False, False, None),
        (True, True, True, None),  # resolved track info always wins: no skip even if a request failed along the way
        (False, False, False, SkipReason.NO_SOURCE_RELEASE_FOUND),
        (False, True, False, SkipReason.LFM_REQUEST_FAILURE),
        (False, False, True, SkipReason.MB_REQUEST_FAILURE),
        (False, True, True, SkipReason.LFM_REQUEST_FAILURE),  # LFM is the primary source, so it wins the attribution
    ],
)
def test_origin_track_skip_reason_attribution(
    make_track_search_item: pytest.FixtureRequest,
    has_track_info: bool,
    lfm_request_failed: bool,
    mb_request_failed: bool,
    expected: SkipReason | None,
) -> None:
    """A missing origin release is attributed to a failed LFM/MB request when one occurred during resolution."""
    mock_si = make_track_search_item(is_lfm_rec=True)
    if has_track_info:
        mock_si.set_origin_candidates([OriginRelease(release_name="r", source=OriginSource.LFM)])
    mock_si.lfm_request_failed = lfm_request_failed
    mock_si.mb_request_failed = mb_request_failed
    assert _origin_track_skip_reason(si=mock_si) == expected


def test_mark_skipped_logs_real_filter_classname(
    make_album_search_item: pytest.FixtureRequest, caplog: pytest.LogCaptureFixture
) -> None:
    """The skip log must name the actual filter class, not its metaclass (regression for `cls.__class__.__name__`)."""
    mock_si = make_album_search_item(is_lfm_rec=False)
    with (
        patch("plastered.release_search.processors.filters.set_result_status"),
        patch("plastered.release_search.processors.filters.persist_search_trace"),
    ):
        with caplog.at_level("DEBUG", logger="plastered.release_search.processors.filters"):
            PostRedSearchFilter._mark_skipped(si=mock_si, skip_reason=SkipReason.NO_MATCH_FOUND)
    assert "filtered by PostRedSearchFilter" in caplog.text
    assert "ABCMeta" not in caplog.text
