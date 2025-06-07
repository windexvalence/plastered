#!/usr/bin/env bash
set -exo pipefail

if [[ -z "$CODE_FORMAT_CHECK" ]]; then
    CHECK=0
else
    CHECK=1
fi

export PYTHONPATH="${APP_DIR}/plastered/"
# isort_config_filepath=$(isort . --show-config | jq -r -c '..|.source? | select( . != null and . != "defaults" and . != "black profile")')
# isort_target_paths=$(isort . --show-config | jq -r -c '. | .src_paths?')
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
