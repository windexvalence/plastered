#!/usr/bin/env bash
set -euo pipefail

source $HOME/.profile
stty cols $COLUMNS &> /dev/null && stty rows $LINES &> /dev/null
export PYTHONPATH="${APP_DIR}/src/python"
python ${APP_DIR}/src/python/plastered/cli.py "$@"
