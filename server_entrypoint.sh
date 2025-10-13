#!/usr/bin/env bash
set -euo pipefail

echo "Attempting to initialize plastered API server ..."
export PYTHONPATH="${APP_DIR}/"

uvicorn plastered.api.server:fastapi_app --host 0.0.0.0 --port 80 --log-level debug
