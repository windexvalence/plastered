from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple
from unittest.mock import MagicMock, call, patch

import pytest

from plastered.config.config_parser import AppConfig
from plastered.run_cache.run_cache import (
    CacheType,
    RunCache,
    _tomorrow_midnight_datetime,
)
from plastered.utils.exceptions import RunCacheDisabledException, RunCacheException
from tests.conftest import api_run_cache, scraper_run_cache, valid_app_config

_DT_STR_FORMAT = "%Y-%m-%d %H:%M:%S"


def _is_none_data_validator(x: Any) -> bool:
    return x is not None


@pytest.mark.parametrize(
    "function_invoked_datetime, expected",
    [
        (  # case 1: Invoked more than 20 before next midnight and result will be in same month.
            datetime.strptime("2025-10-13 12:00:00", _DT_STR_FORMAT),
            datetime.strptime("2025-10-14 00:00:00", _DT_STR_FORMAT),
        ),
        (  # case 2: Invoked more than 20 before next midnight and result will be in following month.
            datetime.strptime("2025-10-31 09:59:00", _DT_STR_FORMAT),
            datetime.strptime("2025-11-01 00:00:00", _DT_STR_FORMAT),
        ),
        (  # case 3: Invoked less than 20 before next midnight and result will be in same month.
            datetime.strptime("2025-01-07 23:59:00", _DT_STR_FORMAT),
            datetime.strptime("2025-01-09 00:00:00", _DT_STR_FORMAT),
        ),
        (  # case 4: Invoked less than 20 before next midnight and result will be in following month.
            datetime.strptime("2025-10-31 23:41:00", _DT_STR_FORMAT),
            datetime.strptime("2025-11-02 00:00:00", _DT_STR_FORMAT),
        ),
        (  # case 5: Invoked right on midnight.
            datetime.strptime("2025-04-20 00:00:00", _DT_STR_FORMAT),
            datetime.strptime("2025-04-21 00:00:00", _DT_STR_FORMAT),
        ),
        (  # case 6: Invoked exactly 20 minutes before midnight
            datetime.strptime("2025-04-20 23:40:00", _DT_STR_FORMAT),
            datetime.strptime("2025-04-22 00:00:00", _DT_STR_FORMAT),
        ),
    ],
)
def test_tomorrow_midnight_datetime(function_invoked_datetime: datetime, expected) -> None:
    # https://docs.python.org/3/library/unittest.mock-examples.html#partial-mocking
    with patch("plastered.run_cache.run_cache.datetime", wraps=datetime) as mock_datetime:
        mock_datetime.now.return_value = function_invoked_datetime
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
        actual = _tomorrow_midnight_datetime()
        assert actual == expected, f"Expected {str(expected)}, but got {str(actual)}"


@pytest.mark.parametrize(
    "enabled, cache_type",
    [
        (False, CacheType.API),
        (True, CacheType.API),
        (False, CacheType.SCRAPER),
        (True, CacheType.SCRAPER),
    ],
)
def test_run_cache_init(
    valid_app_config: AppConfig,
    enabled: bool,
    cache_type: CacheType,
) -> None:
    with patch.object(AppConfig, "is_cache_enabled") as mock_app_conf_is_cache_enabled:
        with patch("plastered.run_cache.run_cache.Cache") as mock_diskcache:
            mock_app_conf_is_cache_enabled.return_value = enabled
            run_cache = RunCache(app_config=valid_app_config, cache_type=cache_type)
            if enabled:
                mock_diskcache.assert_called_once()
            else:
                mock_diskcache.assert_not_called()
            actual_enabled_attr = run_cache.enabled
            assert (
                actual_enabled_attr == enabled
            ), f"Expected run_cach.enabled to be {enabled}, but got {actual_enabled_attr}"


@pytest.mark.parametrize(
    "cache_type, enabled, cache_key, data_validator_fn, mock_cache_entries, expected",
    [
        tuple([cache_type_val, *tup])
        for tup in [
            (  # case 1: disabled cache
                False,
                "my-key",
                lambda x: x is not None,
                {},
                None,
            ),
            (  # case 2: enabled empty cache
                True,
                "my-key",
                lambda x: x is not None,
                {},
                None,
            ),
            (  # case 3: enabled cache without desired key
                True,
                "my-key",
                lambda x: x is not None,
                {"some-other-key": 69},
                None,
            ),
            (  # case 4: enabled cache with key, but with data_validation_fn returning False
                True,
                "my-key",
                lambda x: False,
                {"my-key": 100},
                None,
            ),
            (  # case 5: enabled cache with key, but exception raised during data validation
                True,
                "will-raise-exception",
                lambda x: x / 0,
                {"will-raise-exception": 100},
                None,
            ),
            (  # case 6: enabled cache with key and valid data
                True,
                "my-key",
                lambda x: isinstance(x, int),
                {"my-key": 100},
                100,
            ),
            (  # case 6: enabled cache with key and valid data
                True,
                "my-key",
                lambda x: isinstance(x, int),
                {"my-key": 100},
                100,
            ),
            (  # case 7: enabled cache with tuple-key and valid data
                True,
                ("my", "key"),
                lambda x: isinstance(x, int),
                {("my", "key"): 69},
                69,
            ),
            (  # case 8: enabled cache with tuple-key and valid dict data
                True,
                ("my", "key"),
                lambda x: isinstance(x, dict),
                {("my", "key"): {"my": "dict", "value": "here"}},
                {"my": "dict", "value": "here"},
            ),
        ]
        for cache_type_val in list(CacheType)
    ],
)
def test_run_cache_load_data_if_valid(
    valid_app_config: AppConfig,
    cache_type: CacheType,
    enabled: bool,
    cache_key: Any,
    data_validator_fn: Callable,
    mock_cache_entries: Dict[Any, Any],
    expected: Any,
) -> None:
    mock_diskcache = MagicMock()
    with patch.object(AppConfig, "is_cache_enabled") as mock_app_conf_cache_enabled:
        mock_app_conf_cache_enabled.return_value = enabled
        with patch("plastered.run_cache.run_cache.Cache") as mock_diskcache_constructor:
            mock_diskcache_constructor.return_value = mock_diskcache
            mock_diskcache.stats.return_value = None
            mock_diskcache.expire.return_value = None
            mock_diskcache.get.side_effect = lambda k: mock_cache_entries.get(k)
            run_cache = RunCache(app_config=valid_app_config, cache_type=cache_type)
            actual = run_cache.load_data_if_valid(cache_key=cache_key, data_validator_fn=data_validator_fn)
            assert actual == expected, f"Expected {expected}, but got {actual}"


@pytest.mark.parametrize(
    "cache_type, expire_datetime, fake_now_datetime, expected_seconds",
    [
        (
            CacheType.API,
            datetime.strptime("2025-11-01 00:00:00", _DT_STR_FORMAT),
            datetime.strptime("2025-10-31 23:59:30", _DT_STR_FORMAT),
            30,
        ),
        (
            CacheType.SCRAPER,
            datetime.strptime("2025-11-01 00:00:00", _DT_STR_FORMAT),
            datetime.strptime("2025-10-31 23:59:30", _DT_STR_FORMAT),
            30,
        ),
        (
            CacheType.API,
            datetime.strptime("2025-11-01 00:00:00", _DT_STR_FORMAT),
            datetime.strptime("2025-10-31 23:00:00", _DT_STR_FORMAT),
            3600,
        ),
    ],
)
def test_seconds_to_expiry(
    valid_app_config: AppConfig,
    cache_type: CacheType,
    expire_datetime: datetime,
    fake_now_datetime: datetime,
    expected_seconds: int,
) -> None:
    mock_diskcache = MagicMock()
    with patch.object(AppConfig, "is_cache_enabled") as mock_app_conf_cache_enabled:
        mock_app_conf_cache_enabled.return_value = True
        with patch("plastered.run_cache.run_cache.Cache") as mock_diskcache_constructor:
            mock_diskcache_constructor.return_value = mock_diskcache
            mock_diskcache.stats.return_value = None
            mock_diskcache.expire.return_value = None
            # https://docs.python.org/3/library/unittest.mock-examples.html#partial-mocking
            with patch("plastered.run_cache.run_cache.datetime", wraps=datetime) as mock_datetime:
                mock_datetime.now.return_value = fake_now_datetime
                mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
                run_cache = RunCache(app_config=valid_app_config, cache_type=cache_type)
                run_cache._expiration_datetime = expire_datetime
                actual = run_cache._seconds_to_expiry()
                assert actual == expected_seconds, f"Expected {expected_seconds}, but got {actual}"


@pytest.mark.parametrize(
    "cache_type, test_key, test_data",
    [
        (CacheType.API, "my-fake-key", "my-fake-value"),
        (CacheType.SCRAPER, "my-fake-key", "my-fake-value"),
    ],
)
def test_run_cache_write_data_valid(
    valid_app_config: AppConfig,
    cache_type: CacheType,
    test_key: Any,
    test_data: Any,
) -> None:
    mock_diskcache = MagicMock()
    with patch.object(AppConfig, "is_cache_enabled") as mock_app_conf_cache_enabled:
        mock_app_conf_cache_enabled.return_value = True
        with patch.object(RunCache, "_seconds_to_expiry") as mock_seconds_to_expiry:
            mock_seconds_to_expiry.return_value = 600
            with patch("plastered.run_cache.run_cache.Cache") as mock_diskcache_constructor:
                mock_diskcache_constructor.return_value = mock_diskcache
                mock_diskcache.stats.return_value = None
                mock_diskcache.expire.return_value = None
                mock_diskcache.set.return_value = True
                run_cache = RunCache(app_config=valid_app_config, cache_type=cache_type)
                actual = run_cache.write_data(cache_key=test_key, data=test_data)
                assert actual == True, f"Expected True, but got {actual}"
                mock_diskcache.set.assert_called_once_with(test_key, test_data, expire=600)


@pytest.mark.parametrize(
    "cache_type, test_key, test_data",
    [
        (CacheType.API, "my-fake-key", "my-fake-value"),
        (CacheType.SCRAPER, "my-fake-key", "my-fake-value"),
    ],
)
def test_run_cache_write_data_invalid(
    valid_app_config: AppConfig,
    cache_type: CacheType,
    test_key: Any,
    test_data: Any,
) -> None:
    mock_diskcache = MagicMock()
    with patch.object(AppConfig, "is_cache_enabled") as mock_app_conf_cache_enabled:
        mock_app_conf_cache_enabled.return_value = False
        with patch.object(RunCache, "_seconds_to_expiry") as mock_seconds_to_expiry:
            mock_seconds_to_expiry.return_value = 600
            run_cache = RunCache(app_config=valid_app_config, cache_type=cache_type)
            with pytest.raises(RunCacheDisabledException, match="cache is not enabled"):
                actual = run_cache.write_data(cache_key=test_key, data=test_data)


@pytest.mark.parametrize(
    "cache_type, run_cache_enabled",
    [
        (CacheType.API, False),
        (CacheType.SCRAPER, False),
        (CacheType.API, True),
        (CacheType.SCRAPER, True),
    ],
)
def test_run_cache_clear(
    valid_app_config: AppConfig,
    cache_type: CacheType,
    run_cache_enabled: bool,
) -> None:
    mock_diskcache = MagicMock()
    with patch.object(AppConfig, "is_cache_enabled") as mock_app_conf_cache_enabled:
        mock_app_conf_cache_enabled.return_value = run_cache_enabled
        with patch("plastered.run_cache.run_cache.Cache") as mock_diskcache_constructor:
            mock_diskcache_constructor.return_value = mock_diskcache
            mock_diskcache.stats.return_value = None
            mock_diskcache.expire.return_value = None
            mock_diskcache.clear.return_value = 10
            run_cache = RunCache(app_config=valid_app_config, cache_type=cache_type)
            if not run_cache_enabled:
                with pytest.raises(RunCacheDisabledException, match="cache is not enabled"):
                    actual = run_cache.clear()
            else:
                actual = run_cache.clear()
                mock_diskcache.clear.assert_called_once()


@pytest.mark.parametrize(
    "cache_type, run_cache_enabled, should_fail",
    [
        (CacheType.API, False, True),
        (CacheType.SCRAPER, False, True),
        (CacheType.API, True, False),
        (CacheType.SCRAPER, True, False),
    ],
)
def test_run_cache_check(
    valid_app_config: AppConfig,
    cache_type: CacheType,
    run_cache_enabled: bool,
    should_fail: bool,
) -> None:
    mock_diskcache = MagicMock()
    expected_check_result_no_fail = ["fake warning"]
    with patch.object(AppConfig, "is_cache_enabled") as mock_app_conf_cache_enabled:
        mock_app_conf_cache_enabled.return_value = run_cache_enabled
        with patch("plastered.run_cache.run_cache.Cache") as mock_diskcache_constructor:
            mock_diskcache_constructor.return_value = mock_diskcache
            mock_diskcache.stats.return_value = None
            mock_diskcache.expire.return_value = None
            mock_diskcache.check.return_value = expected_check_result_no_fail
            mock_diskcache.volume.return_value = 10000.0
            run_cache = RunCache(app_config=valid_app_config, cache_type=cache_type)
            if should_fail:
                with pytest.raises(RunCacheDisabledException, match="cache is not enabled"):
                    run_cache.check()
            else:
                actual = run_cache.check()
                assert (
                    actual == expected_check_result_no_fail
                ), f"Expected {expected_check_result_no_fail}, but got {actual}"

        pass  # TODO: implement


@pytest.mark.parametrize(
    "cache_type, run_cache_enabled",
    [
        (CacheType.API, False),
        (CacheType.SCRAPER, False),
        (CacheType.API, True),
        (CacheType.SCRAPER, True),
    ],
)
def test_print_summary_info(
    valid_app_config: AppConfig,
    cache_type: CacheType,
    run_cache_enabled: bool,
) -> None:
    mock_diskcache = MagicMock()

    def _stats_side_effect(*args, **kwargs) -> Optional[Tuple[int, int]]:
        if len(args) > 0 or len(kwargs) > 0:
            return None
        return (69, 420)

    with patch.object(AppConfig, "is_cache_enabled") as mock_app_conf_cache_enabled:
        mock_app_conf_cache_enabled.return_value = run_cache_enabled
        with patch("plastered.run_cache.run_cache.Cache") as mock_diskcache_constructor:
            mock_diskcache_constructor.return_value = mock_diskcache
            mock_diskcache.stats.side_effect = _stats_side_effect
            mock_diskcache.expire.return_value = None
            mock_diskcache.volume.return_value = 10000.0
            run_cache = RunCache(app_config=valid_app_config, cache_type=cache_type)
            if not run_cache_enabled:
                with pytest.raises(RunCacheDisabledException, match="cache is not enabled"):
                    actual = run_cache.print_summary_info()
            else:
                actual = run_cache.print_summary_info()
                mock_diskcache.stats.assert_has_calls([call(enable=True, reset=True), call()])
