#!/usr/bin/env bash
set -euo pipefail

uv run --all-groups --frozen ruff check --force-exclude --config pyproject.toml --fix || {
	echo "❌ ruff check failed. Run 'prek run .:ruff-check'"
	exit 1
}
