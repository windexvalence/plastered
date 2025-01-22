#!/usr/bin/env bash
set -eo pipefail

export PYTHONPATH="${APP_DIR}/"
export TARGET_DOC_FILEPATH="${APP_DIR}/docs/CLI_reference.md"
if [[ -z "${GITHUB_ACTIONS}" ]]; then
    echo "Not running in a github actions environment. Will overrite auto-genned CLI doc with fresh contents."
    export TARGET_DOC_FILEPATH=/project_src_mnt/docs/CLI_reference.md
fi

python "${APP_DIR}/build_scripts/render_cli_markdown.py"
