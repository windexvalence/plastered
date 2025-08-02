from collections.abc import Callable
from contextlib import nullcontext
from unittest.mock import Mock

import pytest
from pytest_httpx import HTTPXMock

from plastered.config.config_parser import AppConfig
from plastered.run_cache.run_cache import RunCache
from plastered.utils.exceptions import RedClientSnatchException
from plastered.utils.httpx_utils.red_snatch_client import RedSnatchAPIClient


@pytest.mark.parametrize(
    "initial_use_fl_tokens, initial_tokens, expected_use_fl_tokens, expected_available_fl_tokens",
    [(False, 0, False, 0), (False, 1, False, 1), (True, 0, False, 0), (True, 1, True, 1)],
)
def test_set_initial_available_fl_tokens(
    disabled_api_run_cache: RunCache,
    valid_app_settings: AppConfig,
    initial_use_fl_tokens: bool,
    initial_tokens: int,
    expected_use_fl_tokens: bool,
    expected_available_fl_tokens: int,
) -> None:
    red_snatch_client = RedSnatchAPIClient(app_settings=valid_app_settings, run_cache=disabled_api_run_cache)
    assert red_snatch_client._available_fl_tokens == 0
    red_snatch_client._use_fl_tokens = initial_use_fl_tokens
    red_snatch_client.set_initial_available_fl_tokens(initial_available_fl_tokens=initial_tokens)
    assert red_snatch_client._use_fl_tokens == expected_use_fl_tokens
    assert red_snatch_client._available_fl_tokens == expected_available_fl_tokens


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize("mock_response_code", [200, 404])
def test_snatch_red_api_no_fl(
    httpx_mock: HTTPXMock, disabled_api_run_cache: RunCache, valid_app_settings: AppConfig, mock_response_code: int
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
    valid_app_settings: AppConfig,
    mock_response_codes: list[int],
    expected_get_params: list[Callable],
    raise_client_exc: bool,
) -> None:
    expected_get_urls = [f"https://redacted.sh/ajax.php?action=download&{params}" for params in expected_get_params]
    for mock_response_code in mock_response_codes:
        httpx_mock.add_response(status_code=mock_response_code)
    expected_throttle_calls = len(expected_get_urls)
    red_snatch_client = RedSnatchAPIClient(app_settings=valid_app_settings, run_cache=disabled_api_run_cache)
    red_snatch_client._use_fl_tokens = True
    red_snatch_client._available_fl_tokens = 100
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
    valid_app_settings: AppConfig,
    mock_snatched_tids: set[str],
    tid_arg: str,
    expected: bool,
) -> None:
    red_snatch_client = RedSnatchAPIClient(app_settings=valid_app_settings, run_cache=disabled_api_run_cache)
    red_snatch_client._tids_snatched_with_fl_tokens = mock_snatched_tids
    actual = red_snatch_client.tid_snatched_with_fl_token(tid=tid_arg)
    assert actual == expected
