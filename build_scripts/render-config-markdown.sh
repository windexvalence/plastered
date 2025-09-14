#!/usr/bin/env bash
set -eo pipefail

export PYTHONPATH="${APP_DIR}/"
DOC_FILENAME="config_reference.md"
export TARGET_DOC_FILEPATH="${APP_DIR}/docs/${DOC_FILENAME}"
if [[ -z "${GITHUB_ACTIONS}" ]]; then
    echo "Not running in a github actions environment. Will overrite auto-genned config doc with fresh contents."
    export TARGET_DOC_FILEPATH="/project_src_mnt/docs/${DOC_FILENAME}"
fi

python "${APP_DIR}/build_scripts/render_config_markdown.py"
