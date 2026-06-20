#!/usr/bin/env bash
set -euo pipefail

# Consolidated mypy runner shared by the prek hook, the Makefile, and CI.
#   * prek invokes this with the changed files as positional args -> type-checks just the changeset.
#   * make / CI invoke it with no file args -> type-checks the full source tree ("."), honoring the
#     mypy `exclude`/config in pyproject.toml.

targets=("$@")
if [ "${#targets[@]}" -eq 0 ]; then
	targets=(.)
fi

uv run --all-groups --frozen mypy --config-file pyproject.toml "${targets[@]}" || {
	echo "❌ Failed mypy type checks."
	exit 1
}
