import os
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from plastered.main import cli
from plastered.utils.constants import PLASTERED_CONFIG_ENVVAR


def test_run_launches_uvicorn_with_config_settings(valid_config_filepath: str) -> None:
    """`plastered run --config <path>` launches uvicorn via the app factory with the config-driven server settings."""
    with patch.dict(os.environ), patch("uvicorn.run") as mock_uvicorn_run:
        result = CliRunner().invoke(cli, ["run", "--config", valid_config_filepath])
    assert result.exit_code == 0, f"Expected `run` to pass but errored: {result.output or result.exception}"
    mock_uvicorn_run.assert_called_once()
    assert mock_uvicorn_run.call_args.args == ("plastered.api.app:create_fastapi_app",)
    kwargs = mock_uvicorn_run.call_args.kwargs
    assert kwargs["factory"] is True
    # These values come from examples/config.yaml's `server` section (+ the workers default).
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 80
    assert kwargs["log_level"] == "debug"
    assert kwargs["workers"] == 1


def test_run_exports_config_path_for_the_app_factory(valid_config_filepath: str) -> None:
    """The CLI-provided config path is propagated via the env var that the app factory's lifespan resolves it from."""
    with patch.dict(os.environ), patch("uvicorn.run"):
        result = CliRunner().invoke(cli, ["run", "--config", valid_config_filepath])
        exported_config_path = os.environ.get(PLASTERED_CONFIG_ENVVAR)
    assert result.exit_code == 0
    assert exported_config_path == os.fspath(Path(valid_config_filepath).resolve())


def test_run_requires_a_config() -> None:
    """`run` errors out (without launching uvicorn) when no --config is provided and the env var is unset."""
    with patch("uvicorn.run") as mock_uvicorn_run:
        result = CliRunner().invoke(cli, ["run"], env={PLASTERED_CONFIG_ENVVAR: None})
    assert result.exit_code != 0
    assert "Missing option" in result.output
    mock_uvicorn_run.assert_not_called()


def test_cli_help() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.output
