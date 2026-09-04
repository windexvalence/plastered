from __future__ import annotations

import logging
from json import JSONDecodeError
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx2

from plastered.models import OriginSource, origin_releases_from_recording
from plastered.utils.constants import MUSICBRAINZ_API_BASE_URL
from plastered.utils.exceptions import MusicBrainzClientException, MusicBrainzRequestFailureException
from plastered.utils.http_clients.base_client import LOGGER, ThrottledAPIBaseClient
from plastered.utils.text_utils import same_name

if TYPE_CHECKING:
    from plastered.config.app_settings import AppSettings
    from plastered.models import OriginRelease

_LOGGER = logging.getLogger(__name__)


def _escape_lucene_phrase(raw_value: str) -> str:
    """Escapes a raw string for embedding inside a quoted Lucene phrase term."""
    return raw_value.replace("\\", "\\\\").replace('"', '\\"')


def _select_searched_release(releases: list[dict[str, Any]], release_name: str) -> dict[str, Any]:
    """
    The release to take from an MB release-search result: among the hits titled like the wanted release, the first
    primary-type Album, else the first of them; when no hit is titled like it, the top-scored hit. Restricting the
    Album preference to same-titled hits keeps a wanted EP/single from resolving to a similarly named album.
    """
    titled_like_wanted = [r for r in releases if same_name(r.get("title") or "", release_name)]
    for release_json in titled_like_wanted:
        primary_type = (release_json.get("release-group") or {}).get("primary-type") or ""
        if primary_type.casefold() == "album":
            return release_json
    return titled_like_wanted[0] if titled_like_wanted else releases[0]


# TODO (later): refactor public `request*` methods to return Pydantic model classes.
class MusicBrainzAPIClient(ThrottledAPIBaseClient):
    """
    MB-specific Subclass of the ThrottledAPIBaseClient for interacting with the MB API.
    Retries limit and throttling period are configured from user config.
    """

    def __init__(self, app_settings: AppSettings):
        super().__init__(
            base_api_url=MUSICBRAINZ_API_BASE_URL,
            max_api_call_retries=app_settings.musicbrainz.musicbrainz_api_max_retries,
            seconds_between_api_calls=app_settings.musicbrainz.musicbrainz_api_seconds_between_calls,
        )
        self._recording_endpoint = "recording"
        self._release_endpoint = "release"

    def request_release_details(self, mbid: str) -> dict[str, Any]:
        """
        Helper method to hit the MusicBrainz release API with retries and rate-limits.
        Returns the JSON response payload on success.
        Raises `MusicBrainzClientException` on an error response, a connection/transport failure that survives the
        transport-level retries, or an unusable (non-JSON) payload — so callers can degrade gracefully (skip the MB
        enrichment for one item) instead of a single flaky upstream call aborting an entire run.
        """
        _LOGGER.debug(f"Searching musicbrainz for release-mbid: '{mbid}' ...")
        # Enforce request throttling before building and submitting the request.
        self._throttle()
        inc_params = "inc=artist-credits+media+labels+release-groups"
        request_url = f"{MUSICBRAINZ_API_BASE_URL}{self._release_endpoint}/{mbid}?{inc_params}"
        try:
            mb_response = self._client.get(url=request_url, headers={"Accept": "application/json"})
        except httpx2.HTTPError as ex:
            raise MusicBrainzRequestFailureException(
                f"Musicbrainz request failed for URL '{request_url}': {ex.__class__.__name__}: {ex}"
            ) from ex
        if mb_response.is_error:
            raise MusicBrainzClientException(
                f"Unexpected Musicbrainz API error encountered for URL '{request_url}'. Status code: {mb_response.status_code}"
            )
        try:
            return mb_response.json()
        except JSONDecodeError as ex:
            raise MusicBrainzRequestFailureException(
                f"Musicbrainz returned a non-JSON payload for URL '{request_url}'."
            ) from ex

    def _request_json_or_none(self, request_url: str) -> dict[str, Any] | None:
        """
        Issues a throttled GET against an MB endpoint URL. Returns the parsed JSON payload, or `None` on an HTTP
        error response (logged as a warning). Raises `MusicBrainzRequestFailureException` on a connection/transport
        failure that survives the transport-level retries or on an unusable (non-JSON) payload, so the caller can
        attribute a missing result to the failed request rather than a genuine no-result.
        """
        # Enforce request throttling before building and submitting the request.
        self._throttle()
        try:
            mb_response = self._client.get(url=request_url, headers={"Accept": "application/json"})
        except httpx2.HTTPError as ex:
            raise MusicBrainzRequestFailureException(
                f"Musicbrainz request failed for URL '{request_url}': {ex.__class__.__name__}: {ex}"
            ) from ex
        if mb_response.is_error:
            LOGGER.warning(
                f"Unexpected Musicbrainz API error encountered for URL '{request_url}'. Status code: {mb_response.status_code}"
            )
            return None
        try:
            return mb_response.json()
        except JSONDecodeError as ex:
            raise MusicBrainzRequestFailureException(
                f"Musicbrainz returned a non-JSON payload for URL '{request_url}'."
            ) from ex

    def search_release_mbid(self, artist_name: str, release_name: str) -> str | None:
        """
        Resolves a release MBID by artist + release name via the MusicBrainz release *search* endpoint:
        https://musicbrainz.org/doc/MusicBrainz_API/Search#Release
        The Lucene-backed search is scored and tolerant of minor naming differences, which makes it a fuzzy fallback
        for items whose LFM info carries no (usable) MBID. Official releases are required — the query is retried
        without that constraint when it matches nothing — and among the same-titled hits a primary-type Album is
        preferred over the top-scored one (see `_select_searched_release`). Returns the chosen release's MBID, or
        `None` when nothing matches (or
        on an HTTP error response). Raises `MusicBrainzRequestFailureException` on a connection/transport failure
        that survives the transport-level retries or on an unusable (non-JSON) payload.
        """
        LOGGER.debug(f"Searching MB for a release MBID for release: '{release_name}' by '{artist_name}' ...")
        base_query = (
            f'release:"{_escape_lucene_phrase(release_name)}" AND artist:"{_escape_lucene_phrase(artist_name)}"'
        )
        for query_str in (f"{base_query} AND status:official", base_query):
            request_url = f"{MUSICBRAINZ_API_BASE_URL}{self._release_endpoint}?query={quote(query_str, safe=':')}&limit=5&fmt=json"
            json_data = self._request_json_or_none(request_url=request_url)
            releases = (json_data.get("releases") or []) if json_data else []
            if releases:
                return _select_searched_release(releases=releases, release_name=release_name).get("id")
        LOGGER.debug(f"MB release search found no results for release: '{release_name}' by '{artist_name}'.")
        return None

    @staticmethod
    def _get_track_search_query_str(
        track_name: str, artist_name: str, artist_mbid: str | None = None, constrained: bool = False
    ) -> str:
        """
        Builds the (URL-quoted) Lucene query for the MB recording search. The artist is matched by MBID when one is
        known, else by name. When `constrained`, the query additionally requires an official release from an Album
        release group, biasing results toward the canonical origin album.
        """
        query_clauses = [f'recording:"{_escape_lucene_phrase(track_name)}"']
        query_clauses.append(f"arid:{artist_mbid}" if artist_mbid else f'artist:"{_escape_lucene_phrase(artist_name)}"')
        if constrained:
            query_clauses.extend(["status:official", "primarytype:album"])
        return quote(" AND ".join(query_clauses), safe=":")

    def lookup_recording_origin_releases(
        self, recording_mbid: str, artist_name: str, artist_mbid: str | None = None
    ) -> list[OriginRelease]:
        """
        Every release the recording appears on, via the MB recording *lookup* endpoint (one precise request, no search
        scoring): https://musicbrainz.org/doc/MusicBrainz_API#Lookups
        Returns an empty list when MB does not serve the recording (e.g. a stale LFM MBID: an HTTP error response) or
        when the recording is not credited to the wanted artist. Raises `MusicBrainzRequestFailureException` on a
        connection/transport failure that survives the transport-level retries or on an unusable (non-JSON) payload.
        """
        LOGGER.debug(f"Looking up the MB releases of recording '{recording_mbid}' by '{artist_name}' ...")
        inc_params = "inc=releases+release-groups+artist-credits"
        request_url = f"{MUSICBRAINZ_API_BASE_URL}{self._recording_endpoint}/{recording_mbid}?{inc_params}&fmt=json"
        json_data = self._request_json_or_none(request_url=request_url)
        if json_data is None:
            return []
        return origin_releases_from_recording(
            recording_json=json_data,
            source=OriginSource.MB_RECORDING_LOOKUP,
            artist_name=artist_name,
            artist_mbid=artist_mbid,
        )

    def search_recording_origin_releases(
        self, track_name: str, artist_name: str, artist_mbid: str | None = None
    ) -> list[OriginRelease]:
        """
        The releases of every recording matching the track, via the MB recording *search* endpoint:
        https://musicbrainz.org/doc/MusicBrainz_API/Search#Recording
        Only recordings titled like the wanted track and credited to the wanted artist contribute candidates. A
        constrained query (requiring an official release from an Album release group) is attempted first; when it
        yields no candidates, the search is retried unconstrained (for tracks that only exist on singles/EPs/etc.).
        Returns an empty list when nothing matches (or on an HTTP error response). Raises
        `MusicBrainzRequestFailureException` on a connection/transport failure that survives the transport-level
        retries or on an unusable (non-JSON) payload.
        """
        LOGGER.debug(f"Searching MB for the recordings of track '{track_name}' by '{artist_name}' ...")
        for constrained in (True, False):
            query_str = self._get_track_search_query_str(
                track_name=track_name, artist_name=artist_name, artist_mbid=artist_mbid, constrained=constrained
            )
            request_url = f"{MUSICBRAINZ_API_BASE_URL}{self._recording_endpoint}?query={query_str}&fmt=json"
            json_data = self._request_json_or_none(request_url=request_url)
            if json_data is None:
                return []
            candidates: list[OriginRelease] = []
            for recording_json in json_data.get("recordings") or []:
                candidates.extend(
                    origin_releases_from_recording(
                        recording_json=recording_json,
                        source=OriginSource.MB_RECORDING_SEARCH,
                        artist_name=artist_name,
                        artist_mbid=artist_mbid,
                        track_name=track_name,
                    )
                )
            if candidates:
                return candidates
        LOGGER.debug(f"MB recording search found no origin releases for track: '{track_name}' by '{artist_name}'.")
        return []
