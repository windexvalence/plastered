"""
This file contains unit tests to ensure that the auto-generated markdown docs from the CLI help commands
are properly in sync with the current CLI code. If not in sync, will error and indicates that the 
`make render-cli-doc` command should be run and the changes committed.
"""

import os

import pytest

from tests.conftest import PROJECT_ABS_PATH

_CLI_DOC_FILEPATH = os.path.join(PROJECT_ABS_PATH, "docs/CLI_reference.md")
_RENDER_DOC_SCRIPT_FILEPATH = os.path.join(PROJECT_ABS_PATH, "build_scripts", "render_cli_markdown.py")


@pytest.mark.releasetest
def test_cli_autodocs_fresh() -> None:
    assert os.path.exists(
        _CLI_DOC_FILEPATH
    ), f"Missing auto-generated CLI doc at {_CLI_DOC_FILEPATH}. Please run `make render-cli-doc` and commit the changes."
    import sys

    sys.path.append(_RENDER_DOC_SCRIPT_FILEPATH)
    from build_scripts.render_cli_markdown import get_markdown_lines

    expected_markdown_lines = [line.rstrip() for line in get_markdown_lines()]

    with open(_CLI_DOC_FILEPATH, "r") as f:
        actual_markdown_lines = [line.rstrip() for line in f.readlines()] + [""]

    assert (
        actual_markdown_lines == expected_markdown_lines
    ), f"Current state of {_CLI_DOC_FILEPATH} is out of date.  Please run `make render-cli-doc` and commit the changes."
