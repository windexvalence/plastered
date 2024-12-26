#!/usr/bin/env bash
set -euo pipefail

source /usr/local/${APP_VIRTUAL_ENV}/bin/activate
# export PATH=$PATH:/usr/bin/geckodriver
export PATH=$PATH:/usr/bin/chromedriver
# export PYTHONPATH="${APP_DIR}/lastfm_recs_scraper/"
export PYTHONPATH="${APP_DIR}/"
pytest -s -vv "${APP_DIR}/tests"
