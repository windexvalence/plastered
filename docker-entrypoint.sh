#!/bin/sh
# Runtime entrypoint for the app image (Dockerfile stage `plastered-app`).
#
# The image defaults to the non-root `plastered` user via the Dockerfile's USER instruction (ids
# from its PUID/PGID ENV defaults), so normally this script just boots the server. Remapping to
# other ids linuxserver.io-style needs root: launch with `--user root -e PUID=<uid> -e PGID=<gid>`
# and this script remaps the `plastered` user to those ids, hands the app's writable paths to it,
# and re-drops privileges before booting the server — the app process itself never runs as root.
set -eu

if [ "$(id -u)" -ne 0 ]; then
    exec /app/plastered.pex run "$@"
fi

echo "[docker-entrypoint] remapping the runtime user to uid:gid ${PUID}:${PGID} and dropping root privileges"

if [ "$(id -g plastered)" -ne "${PGID}" ]; then
    groupmod --non-unique --gid "${PGID}" plastered
fi
if [ "$(id -u plastered)" -ne "${PUID}" ] || [ "$(id -g plastered)" -ne "${PGID}" ]; then
    usermod --non-unique --uid "${PUID}" --gid "${PGID}" plastered
fi

# The app's writable image paths: PEX_ROOT (the venv the PEX extracts into on first boot) and the
# user's home (browser profile/crash dirs).
chown -R plastered:plastered "${PEX_ROOT}" /home/plastered

# The config dir must be writable too (the SQLite DB lives next to config.yaml). It is usually a
# host volume, so chown it to the requested ids like linuxserver images do for /config — but never
# touch '/' and only warn on failure. The downloads dir is deliberately left alone: ensure the
# host directory is writable by PUID:PGID.
if [ -n "${PLASTERED_CONFIG:-}" ]; then
    config_dir="$(dirname -- "${PLASTERED_CONFIG}")"
    if [ "${config_dir}" != "/" ] && [ -d "${config_dir}" ]; then
        chown -R plastered:plastered "${config_dir}" \
            || echo "[docker-entrypoint] WARNING: could not chown ${config_dir}; ensure it is writable by ${PUID}:${PGID}" >&2
    fi
fi

export HOME=/home/plastered
exec setpriv --reuid plastered --regid plastered --init-groups /app/plastered.pex run "$@"
