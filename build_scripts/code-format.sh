#!/usr/bin/env bash
set -eo pipefail

if [[ -z "$CODE_FORMAT_CHECK" ]]; then
    CHECK=0
else
    CHECK=1
fi

. ${VIRTUAL_ENV}/bin/activate
export PYTHONPATH="${APP_DIR}/plastered/"
if [[ -z "${GITHUB_ACTIONS}" ]]; then
    echo "Not running in a github actions environment"
    cd /project_src_mnt
fi
if [[ "$CHECK" == "1" ]]; then
    black --check .
    isort --check .
    pylint --rcfile ./pyproject.toml plastered
    bandit -c ./pyproject.toml -r . --severity-level all -n 1
else
    black .
    isort .
    pylint --rcfile ./pyproject.toml plastered
    bandit -c ./pyproject.toml -r . --severity-level all -n 1
fi
