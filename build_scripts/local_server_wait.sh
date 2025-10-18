#!/usr/bin/env bash
set -euo pipefail

LOCAL_BROWSER_ADDR=http://localhost:8000/
echo "Attempting to open the following page in local browser: ${LOCAL_BROWSER_ADDR} ..."
sleep 2
echo "If the page does not automatically open, enter ${LOCAL_BROWSER_ADDR} into your browser."
open "${LOCAL_BROWSER_ADDR}"
