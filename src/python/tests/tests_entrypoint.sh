#!/usr/bin/env bash
set -eo pipefail

# TODO: if using pytest-xdist, figure out configuring command on optional pdb flag: https://pytest-xdist.readthedocs.io/en/stable/known-limitations.html#debugging
if [ $# -eq 1 ]; then
    if [[ "$1" == "tests" ]]; then
        echo "No test target specified. Running all tests ..."
    else
        echo "Test target specified as '$1' . Will only run that test."
    fi
else
    echo "Invalid number of arguments provided: {$#}. May either indicate a single test to run, provide 'tests' to run all tests." && exit 1
fi

# Collect optional marker flags in an array so empty values are never passed as args -- an empty
# positional arg breaks pytest's initial conftest loading, so `pytest_addoption` never registers
# `--slowtests`/`--releasetests` and pytest then rejects them as "unrecognized arguments".
PYTEST_MARKER_FLAGS=()
# Conditionally run the additional release-only tests if running on a release GH workflow, otherwise don't run the release-only tests.
if [[ -n "${RELEASE_TESTS}" ]]; then
    PYTEST_MARKER_FLAGS+=("--releasetests")
fi
# Conditionally run the additional slow tests if running in a CI build or `--slowtests` explicitly
# passed, otherwise don't run the slow tests by default.
if [[ "${SLOW_TESTS}" == "1" ]] || [[ -n "${GITHUB_ACTIONS}" ]]; then
    PYTEST_MARKER_FLAGS+=("--slowtests")
fi

export PYTHONPATH="${APP_DIR}/src/python"
if [[ -z "${PDB}" ]] || [[ "${PDB}" == "0" ]]; then
    pytest -n auto --dist=loadfile -vv "${PYTEST_MARKER_FLAGS[@]}" "${APP_DIR}/src/python/$1"
else
    pytest -vv "${PYTEST_MARKER_FLAGS[@]}" "${APP_DIR}/src/python/$1"
fi

if [[ -z "${GITHUB_ACTIONS}" ]] && [[ "$1" == "tests" ]]; then
    echo "Not running in a github actions environment. Updating pytest-coverage markdown badge ..."
    coverage_badge_output_path="/docs/image_assets/coverage.svg"
    if [[ -z "${IS_DOCKER}" ]]; then
        coverage_badge_output_path="./docs/image_assets/coverage.svg"
    fi
    coverage-badge -f -o "${coverage_badge_output_path}"
fi
