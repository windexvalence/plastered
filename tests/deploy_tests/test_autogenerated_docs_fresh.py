"""
This file contains unit tests to ensure that the auto-generated markdown docs from the CLI help commands
are properly in sync with the current CLI code. If not in sync, will error and indicates that the
`make render-cli-doc` command should be run and the changes committed.
"""

import os

import pytest

from tests.conftest import PROJECT_ABS_PATH

_DOCS_FILEPATH = os.path.join(PROJECT_ABS_PATH, "docs")
_CLI_DOC_FILEPATH = os.path.join(_DOCS_FILEPATH, "CLI_reference.md")
_CONFIG_DOC_FILEPATH = os.path.join(_DOCS_FILEPATH, "config_reference.md")
_BUILD_SCRIPTS_PATH = os.path.join(PROJECT_ABS_PATH, "build_scripts")
_RENDER_CLI_DOC_SCRIPT_FILEPATH = os.path.join(_BUILD_SCRIPTS_PATH, "render_cli_markdown.py")
_RENDER_CONFIG_DOC_SCRIPT_FILEPATH = os.path.join(_BUILD_SCRIPTS_PATH, "render_config_markdown.py")


@pytest.mark.releasetest
def test_cli_autodocs_fresh() -> None:
    assert os.path.exists(_CLI_DOC_FILEPATH), (
        f"Missing auto-generated CLI doc at {_CLI_DOC_FILEPATH}. Please run `make render-cli-doc` and commit the changes."
    )
    import sys

    sys.path.append(_RENDER_CLI_DOC_SCRIPT_FILEPATH)
    from build_scripts.render_cli_markdown import get_markdown_lines

    expected_markdown_lines = [line.rstrip() for line in get_markdown_lines()]

    with open(_CLI_DOC_FILEPATH) as f:
        actual_markdown_lines = [line.rstrip() for line in f.readlines()] + [""]

    assert actual_markdown_lines == expected_markdown_lines, (
        f"Current state of {_CLI_DOC_FILEPATH} is out of date.  Please run `make render-cli-doc` and commit the changes."
    )


@pytest.mark.releasetest
def test_config_reference_docs_fresh() -> None:
    assert os.path.exists(_CONFIG_DOC_FILEPATH), (
        f"Missing auto-generated CLI doc at {_CONFIG_DOC_FILEPATH}. Please run `make render-config-doc` and commit the changes."
    )
    import sys
    sys.path.append(_RENDER_CONFIG_DOC_SCRIPT_FILEPATH)
    from build_scripts.render_config_markdown import get_md_lines

    expected_md_lines = [line.rstrip() for line in get_md_lines()]

    with open(_CONFIG_DOC_FILEPATH) as f:
        actual_md_lines = [line.rstrip() for line in f.readlines()] + [""]

    assert actual_md_lines == expected_md_lines, (
        f"Current state of {_CONFIG_DOC_FILEPATH} is out of date.  Please run `make render-config-doc` and commit the changes."
    )
