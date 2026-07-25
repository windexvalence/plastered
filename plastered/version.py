import os
from importlib.metadata import PackageNotFoundError, version
from typing import Final

_RELEASE_TAG_ENV_VAR: Final[str] = "PLASTERED_RELEASE_TAG"
_FALLBACK_VERSION: Final[str] = "0.0.0"


def get_project_version() -> str:
    """
    Helper function to return the semver version of Plastered.

    The version is derived from the latest `vX.Y.Z` git tag by setuptools-scm at build / install
    time (see pyproject.toml); it is never maintained by hand. Resolution order:

    1. The installed distribution's metadata — covers dev checkouts (`uv sync` installs the project
       editable) and the app image (the PEX embeds the wheel, whose version is stamped from the
       release tag via SETUPTOOLS_SCM_PRETEND_VERSION).
    2. The PLASTERED_RELEASE_TAG env var — covers the test image, where the project runs from
       sources on PYTHONPATH and is not an installed distribution.
    3. A static fallback for non-release, non-installed contexts.
    """
    try:
        return version("plastered")
    except PackageNotFoundError:
        release_tag = os.getenv(_RELEASE_TAG_ENV_VAR, "")
        return release_tag.removeprefix("v") if release_tag else _FALLBACK_VERSION
