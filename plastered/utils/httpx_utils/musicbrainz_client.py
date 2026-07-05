import logging
from typing import Any
from urllib.parse import quote

from plastered.config.app_settings import AppSettings
from plastered.models import SearchItem
from plastered.utils.constants import MUSICBRAINZ_API_BASE_URL
from plastered.utils.exceptions import MusicBrainzClientException
from plastered.utils.httpx_utils.base_client import LOGGER, ThrottledAPIBaseClient

_LOGGER = logging.getLogger(__name__)


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
        Throws an Exception after `self._max_api_call_retries` consecutive failures.
        """
        _LOGGER.debug(f"Searching musicbrainz for release-mbid: '{mbid}' ...")
        # Enforce request throttling before building and submitting the request.
        self._throttle()
        inc_params = "inc=artist-credits+media+labels+release-groups"
        request_url = f"{MUSICBRAINZ_API_BASE_URL}{self._release_endpoint}/{mbid}?{inc_params}"
        mb_response = self._client.get(url=request_url, headers={"Accept": "application/json"})
        if mb_response.is_error:
            raise MusicBrainzClientException(
                f"Unexpected Musicbrainz API error encountered for URL '{request_url}'. Status code: {mb_response.status_code}"
            )
        return mb_response.json()

    def _get_track_search_query_str(
        self,
        human_readable_track_name: str,
        artist_mbid: str | None = None,
        human_readable_artist_name: str | None = None,
    ) -> str | None:
        search_query_prefix = f"recording:{quote(human_readable_track_name + ' AND ')}"
        if artist_mbid:
            return search_query_prefix + f"arid:{artist_mbid}"
        if human_readable_artist_name:
            return search_query_prefix + f"artist:{quote(human_readable_artist_name)}"
        LOGGER.debug(
            f"Cannot resolve origin release for track rec: '{human_readable_track_name}'. No available artist_mbid or human readable artist name provided."
        )
        return None

    def request_release_details_for_track(
        self, si: SearchItem, artist_mbid: str | None = None
    ) -> dict[str, str | None] | None:
        """
        Helper method specifically for attempting to resolve a release name / MBID from which a track rec originated from
        with retries and rate-limits. The underlying "endpoint" this method requests is MusicBrainz's "recording" search endpoint:
        https://musicbrainz.org/doc/MusicBrainz_API/Search#Recording
        This will only be called if the LFM API does not have a release name already associated with the track rec in question.

        If the origin release name cannot be resolved, returns None since the release name is required for searching on RED.
        Otherwise returns a dict of the the form {"origin_release_mbid": str | None, "origin_release_name": str | None}
        """
        LOGGER.debug(f"Attempting to resolve origin release for track rec: track: '{si.track_name}' ...")
        track_name = si.track_name
        artist_name = si.artist_name
        search_query_str = self._get_track_search_query_str(
            human_readable_track_name=track_name, artist_mbid=artist_mbid, human_readable_artist_name=artist_name
        )
        if not search_query_str:  # pragma: no cover
            return None
        # Enforce request throttling before building and submitting the request.
        self._throttle()
        request_url = f"{MUSICBRAINZ_API_BASE_URL}{self._recording_endpoint}?query={search_query_str}&fmt=json"
        mb_response = self._client.get(url=request_url, headers={"Accept": "application/json"})
        if mb_response.is_error:
            LOGGER.warning(
                f"Unexpected Musicbrainz API error encountered for URL '{request_url}'. Status code: {mb_response.status_code}"
            )
            return None
        json_data = mb_response.json()
        try:
            first_release_match_json = json_data["recordings"][0]["releases"][0]
        except (KeyError, IndexError):
            LOGGER.debug(f"Unable to resolve an origin release for track: '{track_name}' by '{artist_name}'")
            return None
        rel_mbid, rel_name = first_release_match_json.get("id"), first_release_match_json.get("title")
        if not rel_name:
            LOGGER.debug(f"Unable to resolve origin release title for track: '{track_name}' by '{artist_name}'")
            return None
        return {"origin_release_mbid": rel_mbid, "origin_release_name": rel_name}
