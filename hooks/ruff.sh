#!/usr/bin/env bash
set -euo pipefail

# Consolidated `ruff check` + `ruff format` runner shared by the prek hooks and the Makefile/CI.
#   * prek invokes this with the changed files as positional args -> runs against just the changeset.
#   * `make` / CI invoke it with no file args -> runs against the whole valid file set (ruff
#     discovers files via the pyproject config).
# Set RUFF_CHECK_ONLY=1 for non-mutating check mode (used by `make fmt-check` in CI); otherwise ruff
# applies lint auto-fixes and reformats in place.
# `--force-exclude` makes ruff honor the pyproject `exclude` config even for files passed explicitly.

check_cmd=(check --force-exclude --config pyproject.toml)
format_cmd=(format --force-exclude --config pyproject.toml)

if [[ "${RUFF_CHECK_ONLY:-0}" == "1" ]]; then
	format_cmd+=(--check)
else
	check_cmd+=(--fix)
fi

uv run --all-groups --frozen ruff "${check_cmd[@]}" "$@" || {
	echo "❌ ruff check failed."
	exit 1
}

uv run --all-groups --frozen ruff "${format_cmd[@]}" "$@" || {
	echo "❌ ruff format failed."
	exit 1
}
