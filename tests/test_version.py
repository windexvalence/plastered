"""Tests for plastered.version.get_project_version resolution order."""

from pathlib import Path
from unittest.mock import patch

from plastered import version
from plastered.version import get_project_version

_FAKE_PYPROJECT = b'[project]\nname = "plastered"\nversion = "9.9.9-packaged"\n'


def test_get_project_version_prefers_packaged_pyproject(tmp_path: Path) -> None:
    """When a pyproject.toml is packaged inside the plastered package (PEX build), it wins."""
    packaged_dir = tmp_path / "plastered"
    packaged_dir.mkdir()
    (packaged_dir / "pyproject.toml").write_bytes(_FAKE_PYPROJECT)
    with patch.object(version.importlib.resources, "files", return_value=packaged_dir):
        assert get_project_version() == "9.9.9-packaged"


def test_get_project_version_falls_back_to_app_dir_pyproject() -> None:
    """Without a packaged pyproject.toml (source checkout), $APP_DIR/pyproject.toml is read."""
    expected_version = version.toml_load(open(version._PYPROJECT_TOML_FILEPATH, "rb"))["project"]["version"]
    assert get_project_version() == expected_version
