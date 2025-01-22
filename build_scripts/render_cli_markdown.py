import os
from textwrap import dedent
from typing import List, Optional

from mkdocs_click._extension import replace_command_docs
from mkdocs_click._processing import replace_blocks

# NOTE: the mkdocs_click CLI works with generating full mkdocs HTML,
# But we just want plain `.md` files output from that library, so this script
# uses the mkdocs_click lib to handle the static markdown file generation only.
# Heavily adopted from their unit test case here:
# https://github.com/mkdocs/mkdocs-click/blob/c013cb0df7c95c1d8aa2e21c8932d7156e83eba9/tests/test_extension.py#L27-L41


_TARGET_DOC_FILEPATH = os.getenv("TARGET_DOC_FILEPATH")


def get_markdown_lines() -> List[str]:
    mkdocks_click_md_text = dedent(
        """
        ::: mkdocs-click
        :module: plastered.cli
        :command: cli
    """
    ).rstrip()
    mkdocs_options = {
        "module": "plastered.cli",
        "command": "cli",
    }
    # adopted from mkdocs_click internals here:
    # https://github.com/mkdocs/mkdocs-click/blob/master/mkdocs_click/_extension.py#L55
    raw_markdown_lines = list(
        replace_blocks(
            lines=mkdocks_click_md_text.split("\n"),
            title="mkdocs-click",
            replace=lambda **options: replace_command_docs(has_attr_list=False, **mkdocs_options),
        )
    )
    processed_markdown_lines = [
        "# `plastered` CLI Reference",
        "",
        "> NOTE: this doc is auto-generated from the CLI source code. For a more thorough version of this information, run `plastered --help`, as outlined in the user guide.",
    ]
    processed_markdown_lines.extend([line.replace("cli", "plastered") for line in raw_markdown_lines[3:-2]])
    return processed_markdown_lines


def main(is_github_action: Optional[bool] = False) -> None:
    markdown_lines = get_markdown_lines()
    print(f"writing to output filepath: {_TARGET_DOC_FILEPATH} ...")
    if is_github_action:
        pass
    else:
        with open(_TARGET_DOC_FILEPATH, "w") as f:
            f.writelines("\n".join(markdown_lines))

    print("\n".join(markdown_lines))


if __name__ == "__main__":
    main(is_github_action=os.getenv("GITHUB_ACTIONS"))
