import os
import sys

import pytest

TEST_DIR_ABS_PATH = os.path.dirname(os.path.abspath(__file__))
PROJECT_ABS_PATH = os.path.abspath(os.path.join(TEST_DIR_ABS_PATH, os.pardir))
sys.path.append(PROJECT_ABS_PATH)
EXAMPLES_DIR_PATH = os.path.join(PROJECT_ABS_PATH, "examples")

# TODO: add unit tests and ensure project imports work here
@pytest.fixture(scope="session")
def valid_config_filepath() -> str:
    return os.path.join(EXAMPLES_DIR_PATH, "config.yaml")
