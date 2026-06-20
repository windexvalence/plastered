"""
This file contains unit tests to ensure that the
git release tag and the semver id in pyproject.toml are in alignment and both valid.
"""

import os
from tomllib import load as toml_load
from typing import Any

import pytest

from tests.conftest import PROJECT_ABS_PATH

_PYPROJECT_TOML_FILEPATH = os.path.join(PROJECT_ABS_PATH, "pyproject.toml")
_GITHUB_RELEASE_TAG_ENV_VAR = "PLASTERED_RELEASE_TAG"


@pytest.fixture(scope="session")
def pyproject_toml_data() -> dict[str, Any]:
    with open(_PYPROJECT_TOML_FILEPATH, "rb") as f:
        toml_data = toml_load(f)
    return toml_data


@pytest.fixture(scope="session")
def github_release_tag() -> str:
    return os.getenv(_GITHUB_RELEASE_TAG_ENV_VAR)


# TODO: add unit test to check that the `plastered --version` output is also in sync (maybe in the test_cli.py file ?)
@pytest.mark.releasetest
def test_version_id_and_git_tag_match(pyproject_toml_data: dict[str, Any], github_release_tag: str | None) -> None:
    assert github_release_tag is not None, (
        f"Expected a non-empty string value for '{_GITHUB_RELEASE_TAG_ENV_VAR}' environment variable, but got None."
    )
    assert len(github_release_tag) > 0, (
        f"Expected a non-empty string value for '{_GITHUB_RELEASE_TAG_ENV_VAR}' environment variable"
    )
    assert "project" in pyproject_toml_data, "Missing expected top-level 'project' key in pyproject.toml file."
    project_data = pyproject_toml_data["project"]
    assert "version" in project_data, "Missing expected 'version' key in the 'project' section of pyproject.toml file."
    pyproject_version_id = project_data["version"]
    github_release_semver = github_release_tag.removeprefix("v")
    assert pyproject_version_id == github_release_semver, (
        f"Version mismatch detected between pyproject.toml value ({pyproject_version_id}) and GitHub release tag semver ({github_release_semver}). Did you forget to update the version in pyproject.toml?"
    )
