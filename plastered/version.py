import os
from tomllib import load as toml_load

_PROJECT_ABS_PATH = os.path.abspath(os.getenv("APP_DIR"))
_PYPROJECT_TOML_FILEPATH = os.path.join(_PROJECT_ABS_PATH, "pyproject.toml")


def get_project_version() -> str:
    """
    Helper function to return the semver version of
    Plastered, as defined in the pyproject.toml file.
    """
    with open(_PYPROJECT_TOML_FILEPATH, "rb") as f:
        toml_data = toml_load(f)
    return toml_data["project"]["version"]
