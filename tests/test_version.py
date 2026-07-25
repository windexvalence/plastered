"""Tests for plastered.version.get_project_version resolution order."""

from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

import pytest

from plastered import version
from plastered.version import get_project_version


def test_get_project_version_prefers_distribution_metadata() -> None:
    """An installed plastered distribution (dev checkout / PEX image) wins."""
    with patch.object(version, "version", return_value="9.9.9") as mock_version:
        assert get_project_version() == "9.9.9"
    mock_version.assert_called_once_with("plastered")


def test_get_project_version_falls_back_to_release_tag_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without an installed distribution (test image), $PLASTERED_RELEASE_TAG is used, sans the v prefix."""
    monkeypatch.setenv(version._RELEASE_TAG_ENV_VAR, "v9.9.9")
    with patch.object(version, "version", side_effect=PackageNotFoundError):
        assert get_project_version() == "9.9.9"


def test_get_project_version_falls_back_to_static_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without an installed distribution or a release tag env var, the static fallback is returned."""
    monkeypatch.delenv(version._RELEASE_TAG_ENV_VAR, raising=False)
    with patch.object(version, "version", side_effect=PackageNotFoundError):
        assert get_project_version() == version._FALLBACK_VERSION
