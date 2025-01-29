#!/usr/bin/env bash
set -euo pipefail

source $HOME/.profile
stty cols $COLUMNS &> /dev/null && stty rows $LINES &> /dev/null
export PYTHONPATH="${APP_DIR}/"
python ${APP_DIR}/plastered/cli.py "$@"
