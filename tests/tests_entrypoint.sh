#!/usr/bin/env bash
set -euo pipefail

# export PYTHONPATH="${APP_DIR}/lastfm_recs_scraper/"
export PYTHONPATH="${APP_DIR}/"
pytest -s -vv --cov-report term-missing --cov=lastfm_recs_scraper "${APP_DIR}/tests"
if [[ -z "${GITHUB_ACTIONS}" ]]; then
    echo "Not running in a github actions environment. Updating pytest-coverage markdown badge ..."
    coverage-badge -o "/docs/image_assets/coverage.svg"
fi
