import sys
from typing import Generator
from unittest.mock import patch

import pytest


@pytest.fixture(scope="function")
def reset_imports_and_instances() -> Generator[None, None, None]:
    """Fixture which cleans up any imports or singleton instances between test runs."""
    from plastered.api.lifespan_resources import LifespanSingleton

    LifespanSingleton._instance = None

    imported_modules = list(sys.modules.keys())
    for mod in imported_modules:
        if mod.startswith("plastered.api.lifespan_resources"):
            del sys.modules[mod]
    yield
    LifespanSingleton._instance = None


@pytest.mark.no_autouse_mock_lifespan_singleton_inst
def test_get_lifespan_singleton(reset_imports_and_instances: pytest.FixtureRequest) -> None:
    """Ensures the function returns the same instance on each call."""
    from plastered.api.lifespan_resources import get_lifespan_singleton

    first_actual = get_lifespan_singleton()
    assert first_actual is not None
    assert first_actual.__class__.__name__ == "LifespanSingleton"
    second_actual = get_lifespan_singleton()
    assert id(second_actual) == id(first_actual)


@pytest.mark.no_autouse_mock_lifespan_singleton_inst
def test_lifespan_singleton_shutdown(reset_imports_and_instances: pytest.FixtureRequest) -> None:
    """Ensures the LifespanSingleton.shutdown() method works as intended."""
    from plastered.api.lifespan_resources import get_lifespan_singleton

    with patch("plastered.api.lifespan_resources.RedAPIClient") as MockCls:
        lsi = get_lifespan_singleton()
        lsi.shutdown()
        lsi.red_api_client.close_client.assert_called_once()
