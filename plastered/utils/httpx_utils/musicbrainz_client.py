from typing import Any
from urllib.parse import quote

from plastered.config.config_parser import AppConfig
from plastered.run_cache.run_cache import RunCache
from plastered.utils.constants import (
    MUSICBRAINZ_API_BASE_URL,
    PERMITTED_MUSICBRAINZ_API_ENDPOINTS,
)
from plastered.utils.httpx_utils.base_client import LOGGER, ThrottledAPIBaseClient


# TODO (later): refactor public `request*` methods to return Pydantic model classes.
class MusicBrainzAPIClient(ThrottledAPIBaseClient):
    """
    MB-specific Subclass of the ThrottledAPIBaseClient for interacting with the MB API.
    Retries limit and throttling period are configured from user config.
    """

    def __init__(self, app_config: AppConfig, run_cache: RunCache):
        super().__init__(
            base_api_url=MUSICBRAINZ_API_BASE_URL,
            max_api_call_retries=app_config.get_cli_option("musicbrainz_api_max_retries"),
            seconds_between_api_calls=app_config.get_cli_option("musicbrainz_api_seconds_between_calls"),
            run_cache=run_cache,
            valid_endpoints=PERMITTED_MUSICBRAINZ_API_ENDPOINTS,
        )
        self._recording_endpoint = "recording"
        self._release_endpoint = "release"

    def request_release_details(self, mbid: str) -> dict[str, Any]:
        """
        Helper method to hit the MusicBrainz release API with retries and rate-limits.
        Returns the JSON response payload on success.
        Throws an Exception after `self._max_api_call_retries` consecutive failures.
        """
        # Sanity check endpoint then attempt reading from cache
        loaded_from_cache = self._read_from_run_cache(endpoint=self._release_endpoint, params=mbid)
        if loaded_from_cache:
            return loaded_from_cache
        # Enforce request throttling
        self._throttle()
        # Once throttling requirements are met, continue with building and submitting the request
        inc_params = "inc=artist-credits+media+labels+release-groups"
        json_data = self._session.get(
            url=f"{MUSICBRAINZ_API_BASE_URL}{self._release_endpoint}/{mbid}?{inc_params}",
            headers={"Accept": "application/json"},
        ).json()
        cache_write_success = self._write_cache_if_enabled(
            endpoint=self._release_endpoint, params=mbid, result_json=json_data
        )
        LOGGER.debug(f"{self.__class__.__name__}: api cache write status: {cache_write_success}")
        return json_data

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
        self,
        human_readable_track_name: str,
        artist_mbid: str | None = None,
        human_readable_artist_name: str | None = None,
    ) -> dict[str, str | None] | None:
        """
        Helper method specifically for attempting to resolve a release name / MBID from which a track rec originated from
        with retries and rate-limits. The underlying "endpoint" this method requests is MusicBrainz's "recording" search endpoint:
        https://musicbrainz.org/doc/MusicBrainz_API/Search#Recording
        This will only be called if the LFM API does not have a release name already associated with the track rec in question.

        If the origin release name cannot be resolved, returns None since the release name is required for searching on RED.
        Otherwise returns a dict of the the form {"origin_release_mbid": str | None, "origin_release_name": str | None}
        """
        LOGGER.debug(f"Attempting to resolve origin release for track rec: track: '{human_readable_track_name}' ...")
        search_query_str = self._get_track_search_query_str(
            human_readable_track_name=human_readable_track_name,
            artist_mbid=artist_mbid,
            human_readable_artist_name=human_readable_artist_name,
        )
        if not search_query_str:
            return None
        # Sanity check endpoint then attempt reading from cache
        loaded_from_cache = self._read_from_run_cache(endpoint=self._recording_endpoint, params=search_query_str)
        if loaded_from_cache:
            return loaded_from_cache
        # Enforce request throttling
        self._throttle()
        # Once throttling requirements are met, continue with building and submitting the request
        json_data = self._session.get(
            url=f"{MUSICBRAINZ_API_BASE_URL}{self._recording_endpoint}?query={search_query_str}&fmt=json",
            headers={"Accept": "application/json"},
        ).json()
        try:
            first_release_match_json = json_data["recordings"][0]["releases"][0]
        except (KeyError, IndexError):
            LOGGER.debug(
                f"Unable to resolve an origin release for track: '{human_readable_track_name}' by '{human_readable_artist_name}'"
            )
            return None
        rel_mbid, rel_name = first_release_match_json.get("id"), first_release_match_json.get("title")
        if not rel_name:
            LOGGER.debug(
                f"Unable to resolve origin release title for track: '{human_readable_track_name}' by '{human_readable_artist_name}'"
            )
            return None
        release_details = {"origin_release_mbid": rel_mbid, "origin_release_name": rel_name}
        cache_write_success = self._write_cache_if_enabled(
            endpoint=self._recording_endpoint, params=search_query_str, result_json=release_details
        )
        LOGGER.debug(f"{self.__class__.__name__}: api cache write status: {cache_write_success}")
        return release_details
