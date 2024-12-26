#!/usr/bin/env bash
set -euo pipefail

source /usr/local/${APP_VIRTUAL_ENV}/bin/activate
# export PATH=$PATH:/usr/bin/geckodriver
export PATH=$PATH:/usr/bin/chromedriver
export PYTHONPATH="/app/lastfm_recs_scraper/"
# /usr/local/${APP_VIRTUAL_ENV}/bin/pip3 install -r /app/tests/test-requirements.txt
pytest -s -vv /app/tests
