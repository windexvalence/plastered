#!/usr/bin/env bash
set -euo pipefail

uv run --all-groups --frozen bandit -c pyproject.toml -r --severity-level all -n 1 "$@" || {
	echo "❌ Failed bandit security checks."
	exit 1
}
