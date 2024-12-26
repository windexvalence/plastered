#!/usr/bin/env bash
set -eo pipefail

if [[ -z "$CODE_FORMAT_CHECK" ]]; then
    CHECK=0
else
    CHECK=1
fi

source /usr/local/${APP_VIRTUAL_ENV}/bin/activate
export PYTHONPATH="/app/lastfm_recs_scraper/"
cd /app
if [[ "$CHECK" == "1" ]]; then
    black --check /app
    isort --check /app
else
    black /app
    isort /app
fi
