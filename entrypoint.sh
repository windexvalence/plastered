#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="${APP_DIR}/"
python ${APP_DIR}/plastered/cli.py "$@"
