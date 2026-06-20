#!/usr/bin/env bash
set -euo pipefail

uv run --all-groups --frozen ruff format --force-exclude --config pyproject.toml || {
	echo "❌ ruff format modified files. Run 'prek run .:ruff-format'"
	exit 1
}
