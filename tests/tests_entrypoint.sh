#!/usr/bin/env bash
set -exo pipefail

if [[ "${TEST_TARGET}" == "tests" ]]; then
    echo "No test target specified. Running all tests ..."
else
    echo "Test target specified as '$TEST_TARGET' . Will only run that test."
fi

TEST_PATH="${APP_DIR}/$TEST_TARGET"
. ${VIRTUAL_ENV}/bin/activate

export PYTHONPATH="${APP_DIR}/"
# Conditionally run the additional release-only tests if running on a release GH workflow, otherwise don't run the release-only tests.
if [[ -z "${RELEASE_TESTS}" ]]; then
    pytest -s -vv "${TEST_PATH}"
else 
    pytest -s -vv --releasetests "${TEST_PATH}"
fi

if [[ -z "${GITHUB_ACTIONS}" ]] && [[ "$TEST_TARGET" == "tests" ]]; then
    echo "Not running in a github actions environment. Updating pytest-coverage markdown badge ..."
    coverage-badge -f -o "/docs/image_assets/coverage.svg"
fi
