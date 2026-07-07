from dataclasses import dataclass
from pathlib import Path

from plastered.config.app_settings import AppSettings


@dataclass(frozen=True)
class CliState:
    """Wrapper of global CLI settings, passed or inferred from the CLI options."""

    resolved_config_path: Path
    app_settings: AppSettings
