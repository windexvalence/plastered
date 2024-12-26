#!/usr/bin/env bash

# NOTE: this script is a work in progress which has the ultimate goal of pulling the list of recommended albums from last.fm
# and then mapping each of those albums to musicbrainz IDs, which can then be fed into Lidarr for auto-snatching.
# for more info on the last.fm API: https://www.last.fm/api/show/album.getInfo
set -euo pipefail

# USAGE: ./lastfm_recs_to_mbid.sh

LAST_FM_API_KEY=$(cat /mnt/cache/appdata/rword_vault/last_fm_api_key.txt)

if [[ -z "${LAST_FM_API_KEY}" ]]; then
    echo "Must have the 'LAST_FM_API_KEY' environment variable set. Exiting." && exit 1
fi

# TODO: figure out how to programatically pull last.fm recommended albums list

# TODO: write curl request like this
# "http://ws.audioscrobbler.com/2.0/?method=album.getinfo&artist=Polygon%20Window&album=Surfing%20on%20Sine%20Waves&api_key=${LAST_FM_API_KEY}&format=json"

RELEASE_MBID=$(curl "http://ws.audioscrobbler.com/2.0/?method=album.getinfo&artist=Polygon%20Window&album=Surfing%20on%20Sine%20Waves&api_key=${LAST_FM_API_KEY}&format=json" | jq -r '.album.mbid')

# TODO: figure out if there's some plan-b approach for albums with no mbid.
if [[ -z "${RELEASE_MBID}" ]]; then
    echo "No MBID found for artist '' album ''. Exiting." && exit 1
fi

# MB release ID
# "https://musicbrainz.org/release/${RELEASE_MBID}"

# TODO: figure out how to get MB RELEASE GROUP ID from the release ID (which is provided from the lastfm API)
RELEASE_GROUP_MBID=""
# MB release GROUP ID
# "https://musicbrainz.org/release-group/${RELEASE_GROUP_MBID}"

# TODO: check redacted API to make sure ratio is high enough to pull

# TODO: figure out how to get lidarr to monitor and snatch by release ID and/or release group ID over api curl

