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

PYTEST_RELEASE_MARKER_FLAG=""
# Conditionally run the additional release-only tests if running on a release GH workflow, otherwise don't run the release-only tests.
if [[ -n "${RELEASE_TESTS}" ]]; then
    PYTEST_RELEASE_MARKER_FLAG="--releasetests"
fi
PYTEST_SLOW_MARKER_FLAG=""
# Conditionally run the additional slow tests if running in a CI build or `--slowtests` explicitly 
# passed, otherwise don't run the slow tests by default.
if [[ "${SLOW_TESTS}" == "1" ]] || [[ -n "${GITHUB_ACTIONS}" ]]; then
    PYTEST_SLOW_MARKER_FLAG="--slowtests"
fi

export PYTHONPATH="${APP_DIR}/"
pytest -s -vv "${PYTEST_RELEASE_MARKER_FLAG}" "${PYTEST_SLOW_MARKER_FLAG}" "${APP_DIR}/$1"

if [[ -z "${GITHUB_ACTIONS}" ]] && [[ "$1" == "tests" ]]; then
    echo "Not running in a github actions environment. Updating pytest-coverage markdown badge ..."
    coverage-badge -f -o "/docs/image_assets/coverage.svg"
fi
