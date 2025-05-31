from typing import Any, Generator
from unittest.mock import patch

import pytest

from plastered.config.config_parser import AppConfig
from plastered.run_cache.run_cache import CacheType, RunCache


@pytest.fixture(scope="session")
def disabled_api_run_cache(valid_config_filepath: str) -> RunCache:
    """
    Ensure caching doesn't interfere between unit tests for the httpx utils.
    Other test modules should use the `api_run_cache` fixture at top-level conftest.py
    """
    app_config = AppConfig(config_filepath=valid_config_filepath, cli_params=dict())
    with patch.object(AppConfig, "is_cache_enabled") as mock_appconf_cache_enabled:
        mock_appconf_cache_enabled.return_value = False
        disabled_run_cache = RunCache(app_config=app_config, cache_type=CacheType.API)
    return disabled_run_cache
