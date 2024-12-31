#!/usr/bin/env bash
set -euo pipefail

# export PYTHONPATH="${APP_DIR}/lastfm_recs_scraper/"
export PYTHONPATH="${APP_DIR}/"
pytest -s -vv --cov-report term-missing --cov=lastfm_recs_scraper "${APP_DIR}/tests"
