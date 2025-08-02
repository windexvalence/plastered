import datetime
from time import time
from unittest.mock import call, patch

import pytest

from plastered.config.app_settings import AppSettings
from plastered.run_cache.run_cache import RunCache
from plastered.utils.constants import LFM_API_BASE_URL, MUSICBRAINZ_API_BASE_URL, RED_API_BASE_URL
from plastered.utils.httpx_utils.base_client import ThrottledAPIBaseClient, precise_delay
from plastered.utils.httpx_utils.lfm_client import LFMAPIClient
from plastered.utils.httpx_utils.musicbrainz_client import MusicBrainzAPIClient
from plastered.utils.httpx_utils.red_client import RedAPIClient
from plastered.utils.httpx_utils.red_snatch_client import RedSnatchAPIClient


@pytest.mark.slow
@pytest.mark.parametrize("sec_delay", [1, 2, 3, 6])
def test_precise_delay(sec_delay: int) -> None:
    start = time()
    precise_delay(sec_delay=sec_delay)
    end = time()
    actual_delay_time = end - start
    assert actual_delay_time == pytest.approx(sec_delay, abs=0.01)  # Allow for some tolerance in clock precision


@pytest.mark.parametrize(
    "client_throttle_sec, raw_now_timestamps, expected_sleep_call_args",
    [
        (  # CASE 1: all throttle calls are precisely spaced the throttle period. Expect no sleep calls
            5,
            [
                1512345000,  # start ts
                1512345000,  # initial call not blocked
                1512345005,  # +5s
                1512345005,  # call not blocked
                1512345010,  # +5s
                1512345010,  # call not blocked
            ],
            [],
        ),
        (  # CASE 2: all throttle calls are spaced more than the throttle period. Expect no sleep calls
            3,
            [
                1512345000,  # start ts
                1512345000,  # initial call not blocked
                1512345010,  # +10s
                1512345010,  # call not blocked
                1512345016,  # +6s
                1512345016,  # call not blocked
            ],
            [],
        ),
        (  # CASE 3: 2 throttle calls are earlier than the period allows. Expect two sleep calls
            2,
            [
                1736087000,  # start ts
                1736087000,  # initial call not blocked
                1736087003,  # +3s
                1736087003,  # call not blocked
                1736087004,  # +1s
                1736087005,  # call blocked 1s (post-sleep call)
                1736087008,  # +3s
                1736087008,  # call not blocked
                1736087008,  # +0s
                1736087010,  # call blocked 2s (post-sleep call)
            ],
            [1, 2],
        ),
        (  # CASE 4: All throttle calls after initial call are earlier than the period allows. Expect 3 sleep calls
            2,
            [
                1736087000,  # start ts
                1736087000,  # initial call not blocked
                1736087001,  # +1s
                1736087002,  # call blocked 1s (post-sleep call)
                1736087002,  # +0s
                1736087004,  # call blocked 2s (post-sleep call)
                1736087005,  # +1s
                1736087006,  # call blocked 1s (post-sleep call)
            ],
            [1, 2, 1],
        ),
    ],
)
def test_throttle(
    disabled_api_run_cache: RunCache,
    client_throttle_sec: int,
    raw_now_timestamps: list[int],
    expected_sleep_call_args: list[int],
) -> None:
    api_base_client = ThrottledAPIBaseClient(
        base_api_url="https://google.com",
        max_api_call_retries=3,
        seconds_between_api_calls=client_throttle_sec,
        valid_endpoints=set(["fake-endpoint1"]),
        run_cache=disabled_api_run_cache,
    )
    dt_now_call_timestamps = [datetime.datetime.fromtimestamp(raw_ts) for raw_ts in raw_now_timestamps]
    api_base_client._time_of_last_call = dt_now_call_timestamps[0] - datetime.timedelta(hours=1)
    expected_num_throttle_calls = len(dt_now_call_timestamps) // 2
    expected_datetime_now_call_cnt = len(dt_now_call_timestamps)
    # NOTE: mocking datetime is funky. Had to follow this advice: https://stackoverflow.com/a/70598060
    with patch("plastered.utils.httpx_utils.base_client.datetime", wraps=datetime.datetime) as mock_dt:
        mock_dt.now.side_effect = dt_now_call_timestamps
        with patch("plastered.utils.httpx_utils.base_client.precise_delay") as mock_precise_delay:
            mock_precise_delay.return_value = None
            assert api_base_client._throttle_period == datetime.timedelta(seconds=client_throttle_sec)
            for _ in range(expected_num_throttle_calls):
                api_base_client._throttle()
            mock_precise_delay.assert_has_calls(
                [call(sec_delay=expected_arg) for expected_arg in expected_sleep_call_args]
            )
            mock_dt.assert_has_calls([call.now() for _ in range(expected_datetime_now_call_cnt)])


@pytest.mark.parametrize(
    "subclass, endpoint, params",
    [
        (RedAPIClient, "browse", "something=otherthing"),
        (LFMAPIClient, "album.getinfo", "something=otherthing"),
        (MusicBrainzAPIClient, "release", "mbid=69420"),
    ],
)
def test_throttled_api_client_write_cache_valid(
    valid_app_settings: AppSettings,
    enabled_api_run_cache: RunCache,
    subclass: ThrottledAPIBaseClient,
    endpoint: str,
    params: str,
) -> None:
    with patch.object(RunCache, "write_data") as mock_run_cache_write_method:
        mock_run_cache_write_method.return_value = True
        test_client = subclass(app_settings=valid_app_settings, run_cache=enabled_api_run_cache)
        actual = test_client._write_cache_if_enabled(endpoint=endpoint, params=params, result_json={"fake": "value"})
        expected_cache_key = (test_client._base_domain, endpoint, params)
        mock_run_cache_write_method.assert_called_once_with(cache_key=expected_cache_key, data={"fake": "value"})
        assert actual == True


@pytest.mark.parametrize(
    "subclass, cache_enabled, endpoint, params",
    [
        (RedAPIClient, False, "browse", "&something=otherthing"),
        (RedAPIClient, True, "community_stats", "&non-cached-endpoint=nothing&no=cache"),
        (RedAPIClient, True, "user_torrents", "&non-cached-endpoint=nothing&no=cache"),
        (RedSnatchAPIClient, True, "download", "&id=blah"),
        (LFMAPIClient, False, "album.getinfo", "&something=otherthing"),
        (MusicBrainzAPIClient, False, "release", "&something=otherthing"),
    ],
)
def test_throttled_api_client_write_cache_not_valid(
    valid_app_settings: AppSettings,
    enabled_api_run_cache: RunCache,
    subclass: ThrottledAPIBaseClient,
    cache_enabled: bool,
    endpoint: str,
    params: str,
) -> None:
    with patch.object(RunCache, "write_data") as mock_run_cache_write_method:
        with patch.object(RunCache, "write_data") as mock_run_cache_enabled:
            mock_run_cache_write_method.return_value = None
            mock_run_cache_enabled.return_value = cache_enabled
            test_client = subclass(app_settings=valid_app_settings, run_cache=enabled_api_run_cache)
            actual = test_client._write_cache_if_enabled(
                endpoint=endpoint, params=params, result_json={"fake": "value"}
            )
            mock_run_cache_write_method.assert_not_called()
            assert actual == False


@pytest.mark.parametrize(
    "subclass, expected_base_domain",
    [
        (RedAPIClient, RED_API_BASE_URL),
        (LFMAPIClient, LFM_API_BASE_URL),
        (MusicBrainzAPIClient, MUSICBRAINZ_API_BASE_URL),
    ],
)
def test_init_throttled_api_client(
    disabled_api_run_cache: RunCache,
    valid_app_settings: AppSettings,
    subclass: ThrottledAPIBaseClient,
    expected_base_domain: str,
) -> None:
    test_instance = subclass(app_settings=valid_app_settings, run_cache=disabled_api_run_cache)
    assert issubclass(test_instance.__class__, ThrottledAPIBaseClient)
    actual_base_domain = test_instance._base_domain
    assert actual_base_domain == expected_base_domain, (
        f"Expected base domain to be '{expected_base_domain}', but got '{actual_base_domain}'"
    )

    if subclass == RedAPIClient or subclass == RedSnatchAPIClient:
        expected_max_retries = valid_app_settings.red.red_api_retries
        expected_throttle_period = valid_app_settings.red.red_api_seconds_between_calls
    elif subclass == LFMAPIClient:
        expected_max_retries = valid_app_settings.lfm.lfm_api_retries
        expected_throttle_period = valid_app_settings.lfm.lfm_api_seconds_between_calls
    elif subclass == MusicBrainzAPIClient:
        expected_max_retries = valid_app_settings.musicbrainz.musicbrainz_api_max_retries
        expected_throttle_period = valid_app_settings.musicbrainz.musicbrainz_api_seconds_between_calls
    else:
        raise ValueError(
            f"Unexpected class type: {subclass.__name__}. Expected one of RedAPIClient, LFMAPIClient, MusicBrainzAPIClient"
        )

    expected_throttle_period = datetime.timedelta(seconds=expected_throttle_period)
    actual_max_retries = test_instance._max_api_call_retries
    assert actual_max_retries == expected_max_retries, (
        f"Expected max retries to be {expected_max_retries}, but got {actual_max_retries}"
    )
    actual_throttle_period = test_instance._throttle_period
    assert actual_throttle_period == expected_throttle_period, (
        f"Expected throttle period to be {expected_throttle_period}, but got {actual_throttle_period}"
    )
