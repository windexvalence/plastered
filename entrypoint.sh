#!/usr/bin/env bash
set -euo pipefail

source /usr/local/${APP_VIRTUAL_ENV}/bin/activate
# export PATH=$PATH:/usr/bin/geckodriver
export PATH=$PATH:/usr/bin/chromedriver
/usr/local/${APP_VIRTUAL_ENV}/bin/python3 ./lastfm_recs_scraper/cli.py "$@"
