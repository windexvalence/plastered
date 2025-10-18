import logging
import os
from pathlib import Path
from typing import Final

import jsonref
import jsonschema_markdown

from plastered.config.app_settings import AppSettings
from plastered.version import get_project_version

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)

_MARKDOWN_PATH: Final[Path] = Path(os.getenv("TARGET_DOC_FILEPATH"))


def main() -> None:
    md_lines = get_md_lines()
    _LOGGER.info("Writing AppSettings markdown to file ...")
    with open(_MARKDOWN_PATH, "w") as f:
        f.writelines(md_lines)


def get_md_lines() -> list[str]:
    _LOGGER.info("Converting AppSettings JSONSchema to markdown string ...")
    # jsonref.replace_refs used for pydantic workaround described here: https://github.com/pydantic/pydantic/issues/889#issuecomment-2034403278
    md_str = jsonschema_markdown.generate(jsonref.replace_refs(AppSettings.model_json_schema()))
    return _get_md_intro_lines() + [f"{line}\n" for line in md_str.splitlines()]


def _get_md_intro_lines() -> list[str]:
    return [
        f"# `plastered` {get_project_version()} config reference\n",
        "\n",
        "This doc is Auto-generated. If in doubt, refer to `examples/config.yaml`\n",
    ]


if __name__ == "__main__":
    main()
