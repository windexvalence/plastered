"""Tests for `plastered.api.fastapi_dependencies` app-state accessors not yet exercised through a route."""

from unittest.mock import MagicMock

from plastered.api.fastapi_dependencies import get_scrape_scheduler_from_state


def test_get_scrape_scheduler_from_state() -> None:
    mock_request = MagicMock()
    assert get_scrape_scheduler_from_state(mock_request) is mock_request.app.state.scrape_scheduler
