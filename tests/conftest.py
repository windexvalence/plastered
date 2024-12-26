import os
import sys
from typing import Any, Dict

import pytest
import yaml

TEST_DIR_ABS_PATH = os.path.dirname(os.path.abspath(__file__))
PROJECT_ABS_PATH = os.path.abspath(os.getenv("APP_DIR"))
# sys.path.append(PROJECT_ABS_PATH)

from lastfm_recs_scraper.config.config_parser import AppConfig

EXAMPLES_DIR_PATH = os.path.join(PROJECT_ABS_PATH, "examples")


# TODO: add unit tests and ensure project imports work here
@pytest.fixture(scope="session")
def valid_config_filepath() -> str:
    return os.path.join(EXAMPLES_DIR_PATH, "config.yaml")


@pytest.fixture(scope="session")
def valid_config_raw_data(valid_config_filepath: str) -> Dict[str, Any]:
    with open(valid_config_filepath, "r") as f:
        raw_config_data = yaml.safe_load(f.read())
    return raw_config_data


@pytest.fixture(scope="session")
def valid_app_config(valid_config_filepath: str) -> AppConfig:
    return AppConfig(config_filepath=valid_config_filepath, cli_params=dict())
