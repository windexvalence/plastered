#!/usr/bin/env bash
set -euo pipefail

uv lock --check || {
	echo "❌ uv.lock is out of sync. Run 'uv lock'"
	exit 1
}
