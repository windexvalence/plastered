#!/usr/bin/env bash
set -exuo pipefail

echo "Attempting to initialize plastered API server ..."
export PYTHONPATH="${APP_DIR}/"

# main.py's __main__ launches uvicorn with the host / port / log level / workers from the app config.
python "${APP_DIR}/plastered/api/main.py"
