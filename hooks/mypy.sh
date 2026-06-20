#!/usr/bin/env bash
set -euo pipefail

uv run --all-groups --frozen mypy --config-file pyproject.toml "$@" || {
	echo "❌ Failed mypy type checks."
	exit 1
}
