from __future__ import annotations

import logging
from json import JSONDecodeError
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx2

from plastered.utils.constants import MUSICBRAINZ_API_BASE_URL
from plastered.utils.exceptions import MusicBrainzClientException, MusicBrainzRequestFailureException
from plastered.utils.http_clients.base_client import LOGGER, ThrottledAPIBaseClient

if TYPE_CHECKING:
    from plastered.config.app_settings import AppSettings
    from plastered.models import SearchItem

_LOGGER = logging.getLogger(__name__)


def _escape_lucene_phrase(raw_value: str) -> str:
    """Escapes a raw string for embedding inside a quoted Lucene phrase term."""
    return raw_value.replace("\\", "\\\\").replace('"', '\\"')


def _is_official_album_release(release_json: dict[str, Any]) -> bool:
    """Whether a release object of an MB recording-search response is an official, titled Album release."""
    release_group_json = release_json.get("release-group") or {}
    return bool(
        release_json.get("title")
        and release_json.get("status") == "Official"
        and release_group_json.get("primary-type") == "Album"
    )


def _release_date_sort_key(release_json: dict[str, Any]) -> tuple[bool, str]:
    """Sort key ordering releases earliest-date-first, with undated releases last."""
    release_date = release_json.get("date") or ""
    return (not release_date, release_date)


def _select_origin_release(json_data: dict[str, Any]) -> dict[str, str | None] | None:
    """
    Picks the origin release from an MB recording-search response. Recordings are visited in MB's (score-ordered)
    order; the first recording carrying any official Album release wins, and the earliest-dated such release is
    chosen (the canonical original album rather than an arbitrary compilation/single). When no recording has an
    official Album release, falls back to the first release of the first recording.
    """
    recordings = json_data.get("recordings") or []
    for recording_json in recordings:
        official_albums = [rel for rel in (recording_json.get("releases") or []) if _is_official_album_release(rel)]
        if official_albums:
            earliest = min(official_albums, key=_release_date_sort_key)
            return {"origin_release_mbid": earliest.get("id"), "origin_release_name": earliest["title"]}
    try:
        first_release_match_json = recordings[0]["releases"][0]
    except KeyError, IndexError:
        return None
    if not first_release_match_json.get("title"):
        return None
    return {
        "origin_release_mbid": first_release_match_json.get("id"),
        "origin_release_name": first_release_match_json["title"],
    }


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

    def _request_search_json(self, request_url: str) -> dict[str, Any] | None:
        """
        Issues a throttled GET against an MB search endpoint URL. Returns the parsed JSON payload, or `None` on an
        HTTP error response (logged as a warning). Raises `MusicBrainzRequestFailureException` on a
        connection/transport failure that survives the transport-level retries or on an unusable (non-JSON) payload,
        so the caller can attribute a missing result to the failed request rather than a genuine no-result.
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
        for items whose LFM info carries no MBID. Returns the top-scored result's MBID, or `None` when nothing
        matches (or on an HTTP error response). Raises `MusicBrainzRequestFailureException` on a connection/transport
        failure that survives the transport-level retries or on an unusable (non-JSON) payload.
        """
        LOGGER.debug(f"Searching MB for a release MBID for release: '{release_name}' by '{artist_name}' ...")
        query_str = f'release:"{_escape_lucene_phrase(release_name)}" AND artist:"{_escape_lucene_phrase(artist_name)}"'
        request_url = (
            f"{MUSICBRAINZ_API_BASE_URL}{self._release_endpoint}?query={quote(query_str, safe=':')}&limit=5&fmt=json"
        )
        json_data = self._request_search_json(request_url=request_url)
        releases = (json_data.get("releases") or []) if json_data else []
        if not releases:
            LOGGER.debug(f"MB release search found no results for release: '{release_name}' by '{artist_name}'.")
            return None
        return releases[0].get("id")

    def _get_track_search_query_str(
        self,
        human_readable_track_name: str,
        artist_mbid: str | None = None,
        human_readable_artist_name: str | None = None,
        constrained: bool = False,
    ) -> str | None:
        """
        Builds the (URL-quoted) Lucene query for the MB recording search. When `constrained`, the query additionally
        requires an official release from an Album release group, biasing results toward the canonical origin album.
        """
        query_clauses = [f'recording:"{_escape_lucene_phrase(human_readable_track_name)}"']
        if artist_mbid:
            query_clauses.append(f"arid:{artist_mbid}")
        elif human_readable_artist_name:
            query_clauses.append(f'artist:"{_escape_lucene_phrase(human_readable_artist_name)}"')
        else:
            LOGGER.debug(
                f"Cannot resolve origin release for track rec: '{human_readable_track_name}'. No available artist_mbid or human readable artist name provided."
            )
            return None
        if constrained:
            query_clauses.extend(["status:official", "primarytype:album"])
        return quote(" AND ".join(query_clauses), safe=":")

    def request_release_details_for_track(
        self, si: SearchItem, artist_mbid: str | None = None
    ) -> dict[str, str | None] | None:
        """
        Helper method specifically for attempting to resolve a release name / MBID from which a track rec originated from
        with retries and rate-limits. The underlying "endpoint" this method requests is MusicBrainz's "recording" search endpoint:
        https://musicbrainz.org/doc/MusicBrainz_API/Search#Recording
        This will only be called if the LFM API does not have a release name already associated with the track rec in question.

        A constrained query (requiring an official release from an Album release group) is attempted first; when it
        yields nothing, the search is retried without the constraints (for tracks that only exist on singles/EPs/etc.).
        From the resulting recordings, the earliest official Album release is preferred — see `_select_origin_release`.

        If the origin release name cannot be resolved, returns None since the release name is required for searching on RED.
        Otherwise returns a dict of the the form {"origin_release_mbid": str | None, "origin_release_name": str | None}.
        Raises `MusicBrainzRequestFailureException` on a connection/transport failure that survives the
        transport-level retries or on an unusable (non-JSON) payload, so the caller can attribute the missing origin
        release to the failed request rather than a genuine no-result.
        """
        LOGGER.debug(f"Attempting to resolve origin release for track rec: track: '{si.track_name}' ...")
        track_name = si.track_name
        artist_name = si.artist_name
        for constrained in (True, False):
            search_query_str = self._get_track_search_query_str(
                human_readable_track_name=track_name,
                artist_mbid=artist_mbid,
                human_readable_artist_name=artist_name,
                constrained=constrained,
            )
            if not search_query_str:  # pragma: no cover
                return None
            request_url = f"{MUSICBRAINZ_API_BASE_URL}{self._recording_endpoint}?query={search_query_str}&fmt=json"
            json_data = self._request_search_json(request_url=request_url)
            if json_data is None:
                return None
            if origin_release := _select_origin_release(json_data=json_data):
                return origin_release
        LOGGER.debug(f"Unable to resolve an origin release for track: '{track_name}' by '{artist_name}'")
        return None
