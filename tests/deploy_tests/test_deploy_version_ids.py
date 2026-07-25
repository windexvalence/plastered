"""
This file contains unit tests to ensure that release builds are stamped with a valid `vX.Y.Z`
release tag and that the runtime-reported version matches it. The version is derived from the git
tag by setuptools-scm (see pyproject.toml) — there is no hand-maintained version to check.
"""

import os
import re

import pytest

from plastered.version import get_project_version

_GITHUB_RELEASE_TAG_ENV_VAR = "PLASTERED_RELEASE_TAG"
_RELEASE_TAG_PATTERN = re.compile(r"^v\d+\.\d+\.\d+$")


@pytest.fixture(scope="session")
def github_release_tag() -> str | None:
    return os.getenv(_GITHUB_RELEASE_TAG_ENV_VAR)


@pytest.mark.releasetest
def test_release_tag_is_valid_and_matches_runtime_version(github_release_tag: str | None) -> None:
    assert github_release_tag is not None, (
        f"Expected a non-empty string value for '{_GITHUB_RELEASE_TAG_ENV_VAR}' environment variable, but got None."
    )
    assert _RELEASE_TAG_PATTERN.match(github_release_tag), (
        f"Expected '{_GITHUB_RELEASE_TAG_ENV_VAR}' to be of the form vMAJOR.MINOR.PATCH, but got '{github_release_tag}'."
    )
    release_semver = github_release_tag.removeprefix("v")
    runtime_version = get_project_version()
    assert runtime_version == release_semver, (
        f"Version mismatch detected between the runtime-reported version ({runtime_version}) and the GitHub release tag semver ({release_semver})."
    )
