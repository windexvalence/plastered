#!/usr/bin/env bash
set -exuo pipefail

echo "Attempting to initialize plastered API server ..."
export PYTHONPATH="${APP_DIR}/"

# The `run` command resolves the config path from the PLASTERED_CONFIG env var and launches uvicorn with the
# host / port / log level / workers from the app config.
python "${APP_DIR}/plastered/main.py" run
