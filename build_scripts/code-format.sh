#!/usr/bin/env bash
set -eo pipefail

if [[ -z "$CODE_FORMAT_CHECK" ]]; then
    CHECK=0
else
    CHECK=1
fi

export PYTHONPATH="${APP_DIR}/lastfm_recs_scraper/"
cd /project_src_mnt
if [[ "$CHECK" == "1" ]]; then
    black --check .
    isort --check .
else
    black .
    isort .
fi
