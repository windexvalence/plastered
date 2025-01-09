#!/usr/bin/env bash
set -eo pipefail

if [ $# -eq 1 ]; then
    if [[ "$1" == "tests" ]]; then
        echo "No test target specified. Running all tests ..."
    else
        echo "Test target specified as '$1' . Will only run that test."
    fi
else
    echo "Invalid number of arguments provided: {$#}. May either indicate a single test to run, provide 'tests' to run all tests." && exit 1
fi

# export PYTHONPATH="${APP_DIR}/lastfm_recs_scraper/"
export PYTHONPATH="${APP_DIR}/"
# pytest -s -vv --cov-report term-missing --cov=lastfm_recs_scraper "${APP_DIR}/tests"
pytest -s -vv "${APP_DIR}/$1"
if [[ -z "${GITHUB_ACTIONS}" ]] && [[ "$1" == "tests" ]]; then
    echo "Not running in a github actions environment. Updating pytest-coverage markdown badge ..."
    coverage-badge -f -o "/docs/image_assets/coverage.svg"
fi
