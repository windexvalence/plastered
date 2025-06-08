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
    uv run ruff check
    uv run ruff format --check
    uv run bandit -c ./pyproject.toml -r . --severity-level all -n 1
else
    uv run ruff check --fix
    uv run ruff format
    uv run bandit -c ./pyproject.toml -r . --severity-level all -n 1
fi
