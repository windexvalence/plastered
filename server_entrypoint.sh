#!/usr/bin/env bash
set -exuo pipefail

echo "Attempting to initialize plastered API server ..."
export PYTHONPATH="${APP_DIR}/src/python"

uvicorn plastered.api.main:fastapi_app --host 0.0.0.0 --port 80 --log-level debug
