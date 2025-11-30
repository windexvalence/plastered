#!/usr/bin/env bash
set -euo pipefail

HTMX_LOCAL_FILEPATH="./plastered/api/static/js/htmx.min.js"

download_local_test_asset() {
    local source_url="$1"
    local dest_filepath="$2"
    if [[ ! -f "${dest_filepath}" ]]; then
        wget -O "${dest_filepath}" "${source_url}"
    fi
}

HTMX_VERSION="$(cat Dockerfile | sed -rn 's/.*HTMX_VERSION=([0-9\.]+).*$/\1/p')"
HTMX_FILENAME="$(cat Dockerfile | sed -rn 's/.*HTMX_FILENAME=([a-z\.]+).*$/\1/p')"
download_local_test_asset "https://raw.githubusercontent.com/bigskysoftware/htmx/refs/tags/v${HTMX_VERSION}/dist/${HTMX_FILENAME}" "${HTMX_LOCAL_FILEPATH}"
