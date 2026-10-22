from __future__ import annotations

import logging
from json import JSONDecodeError
from typing import TYPE_CHECKING, Any
from urllib.parse import quote_plus

import httpx2

from plastered.models import RedUserDetails
from plastered.models.red_models import ReleaseEntry
from plastered.utils.constants import RED_API_BASE_URL, RED_JSON_RESPONSE_KEY
from plastered.utils.exceptions import RedClientException, RedRequestFailureException, RedUserDetailsInitError
from plastered.utils.http_clients.base_client import ThrottledAPIBaseClient

if TYPE_CHECKING:
    from plastered.config.app_settings import AppSettings

_LOGGER = logging.getLogger(__name__)


class RedAPIClient(ThrottledAPIBaseClient):
    """
    RED-specific Subclass of the ThrottledAPIBaseClient for interacting with the RED API.
    Retries limit and throttling period are configured from user config.
    """

    def __init__(self, app_settings: AppSettings):
        super().__init__(
            base_api_url=RED_API_BASE_URL,
            max_api_call_retries=app_settings.red.red_api_retries,
            seconds_between_api_calls=app_settings.red.red_api_seconds_between_calls,
        )
        self._client.headers.update({"Authorization": app_settings.red.red_api_key.get_secret_value()})
        self._red_user_id = app_settings.red.red_user_id
        self._red_user_details: RedUserDetails | None = None

    def request_api(self, action: str, params: str) -> dict[str, Any]:
        """
        Helper method to hit the RED API with retries and rate-limits.
        Returns the JSON response payload on success.
        5xx responses (e.g. the tracker's nginx 503 maintenance page) are retried up to `max_api_call_retries`
        times, spaced by the throttle period, since the transport-level retries only cover connection errors.
        Raises `RedRequestFailureException` on a connection/transport failure that survives the transport-level
        retries or on a non-JSON payload, and the base `RedClientException` on an error status that survives the
        retries. Raises `KeyError` when the JSON payload lacks the top-level response key (RED's failure payload).
        """
        url = f"{RED_API_BASE_URL}?action={action}&{params}"
        for attempt_number in range(1, self._max_api_call_retries + 1):
            # Enforce request throttling before submitting each attempt.
            self._throttle()
            try:
                response = self._client.get(url=url)
            except httpx2.HTTPError as ex:
                raise RedRequestFailureException(
                    f"RED request failed for action '{action}' and params '{params}': {ex.__class__.__name__}: {ex}"
                ) from ex
            if not response.is_server_error:
                break
            _LOGGER.warning(
                f"RED API returned status {response.status_code} for action '{action}' "
                f"(attempt {attempt_number}/{self._max_api_call_retries})."
            )
        if response.is_error:
            raise RedClientException(
                f"Unexpected RED API error encountered for action '{action}' and params '{params}'. "
                f"Status code: {response.status_code}"
            )
        try:
            json_data = response.json()
        except JSONDecodeError as ex:
            raise RedRequestFailureException(
                f"RED returned a non-JSON payload for action '{action}' and params '{params}'."
            ) from ex
        if RED_JSON_RESPONSE_KEY not in json_data:
            raise KeyError(f"RED response JSON missing expected '{RED_JSON_RESPONSE_KEY}' key. JSON: '{json_data}'")
        return json_data[RED_JSON_RESPONSE_KEY]

    def get_artist_release_groups(self, artist_name: str) -> list[ReleaseEntry]:
        """
        Fetches every release group (and its torrents) for an artist via the `ajax.php?action=artist` endpoint.
        Returns an empty list when RED has no entry for the artist name. Matching the wanted release against these
        groups (by title/year/release-type) happens client-side — see `SearchState.get_candidate_release_groups` —
        since RED's search offers no fuzzy matching.
        """
        try:
            raw_artist_resp = self.request_api(action="artist", params=f"artistname={quote_plus(artist_name)}")
        except KeyError:
            # RED responds with a failure payload carrying no top-level response key when the artist does not exist.
            _LOGGER.info(f"RED has no artist entry matching '{artist_name}'.")
            return []
        return [
            ReleaseEntry.from_artist_torrent_group_json_blob(json_blob=blob)
            for blob in raw_artist_resp.get("torrentgroup", [])
        ]

    def get_red_user_details(self) -> RedUserDetails:
        """
        Helper method wrapping multiple RED API calls to generate the instance of
        `plastered.models.red_models.RedUserDetails`. All the underlying calls are essentially only called in one go
        per application run to get the initial state of pre-snatched releases and ratio stats.
        """
        if self._red_user_details is not None:  # pragma: no cover
            return self._red_user_details
        _LOGGER.debug(f"Gathering RED api responses to init RedUserDetails for user ID: '{self._red_user_id}' ...")
        snatch_cnt, seed_cnt = self._rud_helper(action="community_stats")
        snatched_torrents_list = self._rud_helper(action="user_torrents", type_="snatched", lim=snatch_cnt)
        seeding_torrents_list = self._rud_helper(action="user_torrents", type_="seeding", lim=seed_cnt)
        user_profile_json = self._rud_helper(action="user")
        _LOGGER.debug("Completed calling RED user info endpoints, returning RedUserDetails instance ...")
        return RedUserDetails(
            user_id=self._red_user_id,
            snatched_count=snatch_cnt,
            snatched_torrents_list=snatched_torrents_list + seeding_torrents_list,
            user_profile_json=user_profile_json,
        )

    def _rud_helper(self, action: str, type_: str | None = None, lim: int | None = None) -> Any:
        def _post_process(raw: dict[str, Any]) -> Any:
            if action == "community_stats":
                return (int(raw["snatched"].replace(",", "")), int(raw["seeding"].replace(",", "")))
            elif action == "user_torrents":
                return raw[type_]  # type: ignore[index]
            else:
                return raw

        req_params = f"userid={self._red_user_id}" if action == "community_stats" else f"id={self._red_user_id}"
        try:
            if action == "user_torrents":
                if type_ is None or lim is None:  # pragma: no cover
                    raise ValueError("type_ and limit must be non-None when requesting with user_torrents action.")
                req_params += f"&type={type_}&limit={lim}&offset=0"
            unprocessed_dict = self.request_api(action=action, params=req_params)
            return _post_process(unprocessed_dict)
        except Exception as ex:
            _LOGGER.error("RedUserDetails creation failed", exc_info=True)
            raise RedUserDetailsInitError(failed_step=action + (f"-{type_}" if type_ else "")) from ex
