import importlib.resources
import os
from pathlib import Path
from tomllib import load as toml_load
from typing import Final

_PROJECT_ABS_PATH: Final[Path] = Path(os.path.abspath(os.getenv("APP_DIR", ".")))
_PYPROJECT_TOML_FILEPATH: Final[Path] = _PROJECT_ABS_PATH / "pyproject.toml"


# TODO: replace this with a more idiomatic version inference and return value
def get_project_version() -> str:
    """
    Helper function to return the semver version of
    Plastered, as defined in the pyproject.toml file.

    Prefers a pyproject.toml packaged inside the `plastered` package itself (present in packaged
    builds, e.g. the PEX image, where no repo root exists); falls back to $APP_DIR/pyproject.toml
    (a source checkout).
    """
    packaged = importlib.resources.files("plastered").joinpath("pyproject.toml")
    if packaged.is_file():
        with packaged.open("rb") as f:
            toml_data = toml_load(f)
    else:
        with open(_PYPROJECT_TOML_FILEPATH, "rb") as f:
            toml_data = toml_load(f)
    return toml_data["project"]["version"]
