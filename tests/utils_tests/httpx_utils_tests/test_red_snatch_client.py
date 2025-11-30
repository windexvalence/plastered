from collections.abc import Callable
from contextlib import nullcontext
from unittest.mock import Mock

import pytest
from pytest_httpx import HTTPXMock

from plastered.config.app_settings import AppSettings
from plastered.models.red_models import RedUserDetails
from plastered.run_cache.run_cache import RunCache
from plastered.utils.exceptions import RedClientSnatchException
from plastered.utils.httpx_utils.red_snatch_client import RedSnatchAPIClient


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize("mock_response_code", [200, 404])
def test_snatch_red_api_no_fl(
    httpx_mock: HTTPXMock, disabled_api_run_cache: RunCache, valid_app_settings: AppSettings, mock_response_code: int
) -> None:
    httpx_mock.add_response(status_code=mock_response_code)
    red_snatch_client = RedSnatchAPIClient(app_settings=valid_app_settings, run_cache=disabled_api_run_cache)
    red_snatch_client._throttle = Mock(name="_throttle")
    red_snatch_client._throttle.return_value = None
    with pytest.raises(RedClientSnatchException) if mock_response_code != 200 else nullcontext():
        red_snatch_client.snatch(tid="69", can_use_token=False)
    red_snatch_client._throttle.assert_called_once()


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize(
    "mock_response_codes, expected_get_params, raise_client_exc",
    [
        ([200], ["id=69&usetoken=1"], False),
        ([404, 200], ["id=69&usetoken=1", "id=69"], False),
        ([404, 404], ["id=69&usetoken=1", "id=69"], True),
        ([500, 404], ["id=69&usetoken=1", "id=69"], True),
    ],
    ids=["200_first_try", "200_second_try", "404_all", "500_404"],
)
def test_snatch_red_api_use_token(
    httpx_mock: HTTPXMock,
    disabled_api_run_cache: RunCache,
    valid_app_settings: AppSettings,
    mock_red_user_details: RedUserDetails,
    mock_response_codes: list[int],
    expected_get_params: list[Callable],
    raise_client_exc: bool,
) -> None:
    expected_get_urls = [f"https://redacted.sh/ajax.php?action=download&{params}" for params in expected_get_params]
    for mock_response_code in mock_response_codes:
        httpx_mock.add_response(status_code=mock_response_code)
    expected_throttle_calls = len(expected_get_urls)
    red_snatch_client = RedSnatchAPIClient(app_settings=valid_app_settings, run_cache=disabled_api_run_cache)
    red_snatch_client._red_user_details = mock_red_user_details
    red_snatch_client._use_fl_tokens = True
    red_snatch_client._throttle = Mock(name="_throttle")
    red_snatch_client._throttle.return_value = None
    with pytest.raises(RedClientSnatchException) if raise_client_exc else nullcontext():
        result = red_snatch_client.snatch(tid="69", can_use_token=True)
    actual_requests = httpx_mock.get_requests()
    assert len(actual_requests) == len(expected_get_urls)
    for i, expected_get_url in enumerate(expected_get_urls):
        assert str(actual_requests[i].url) == expected_get_url
    actual_throttle_calls = len(red_snatch_client._throttle.mock_calls)
    assert actual_throttle_calls == expected_throttle_calls, (
        f"Expected {expected_throttle_calls}, but found {actual_throttle_calls}"
    )


@pytest.mark.parametrize(
    "mock_snatched_tids, tid_arg, expected",
    [
        (set(), "abc", False),
        (set(["abc"]), "def", False),
        (set(["abc"]), "abc", True),
        (set(["abc", "def"]), "123", False),
        (set(["abc", "def", "123"]), "abc", True),
    ],
)
def test_tid_snatched_with_fl_token(
    disabled_api_run_cache: RunCache,
    valid_app_settings: AppSettings,
    mock_snatched_tids: set[str],
    tid_arg: str,
    expected: bool,
) -> None:
    red_snatch_client = RedSnatchAPIClient(app_settings=valid_app_settings, run_cache=disabled_api_run_cache)
    red_snatch_client._tids_snatched_with_fl_tokens = mock_snatched_tids
    actual = red_snatch_client.tid_snatched_with_fl_token(tid=tid_arg)
    assert actual == expected
