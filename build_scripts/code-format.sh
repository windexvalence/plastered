#!/usr/bin/env bash
set -exo pipefail

if [[ -z "$CODE_FORMAT_CHECK" ]]; then
    CHECK=0
else
    CHECK=1
fi

export PYTHONPATH="${APP_DIR}/plastered/"
if [[ -z "${GITHUB_ACTIONS}" ]]; then
    echo "Not running in a github actions environment"
    cd /project_src_mnt
fi
if [[ "$CHECK" == "1" ]]; then
    ruff check
    ruff format --check
    bandit -c ./pyproject.toml -r . --severity-level all -n 1
else
    ruff check --fix
    ruff format
    bandit -c ./pyproject.toml -r . --severity-level all -n 1
fi
