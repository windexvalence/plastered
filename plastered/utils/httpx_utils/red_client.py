import logging
from typing import Any

from plastered.config.app_settings import AppSettings
from plastered.models.red_models import RedUserDetails
from plastered.run_cache.run_cache import RunCache
from plastered.utils.constants import (
    NON_CACHED_RED_API_ENDPOINTS,
    PERMITTED_RED_API_ENDPOINTS,
    RED_API_BASE_URL,
    RED_JSON_RESPONSE_KEY,
)
from plastered.utils.exceptions import RedUserDetailsInitError
from plastered.utils.httpx_utils.base_client import LOGGER, ThrottledAPIBaseClient

_LOGGER = logging.getLogger(__name__)


class RedAPIClient(ThrottledAPIBaseClient):
    """
    RED-specific Subclass of the ThrottledAPIBaseClient for interacting with the RED API.
    Retries limit and throttling period are configured from user config.
    """

    def __init__(self, app_settings: AppSettings, run_cache: RunCache | None = None):
        super().__init__(
            base_api_url=RED_API_BASE_URL,
            max_api_call_retries=app_settings.red.red_api_retries,
            seconds_between_api_calls=app_settings.red.red_api_seconds_between_calls,
            valid_endpoints=set(PERMITTED_RED_API_ENDPOINTS),
            run_cache=run_cache,
            non_cached_endpoints=set(NON_CACHED_RED_API_ENDPOINTS),
        )
        self._client.headers.update({"Authorization": app_settings.red.red_api_key.get_secret_value()})
        self._red_user_id = app_settings.red.red_user_id

    def request_api(self, action: str, params: str) -> dict[str, Any]:
        """
        Helper method to hit the RED API with retries and rate-limits.
        Returns the JSON response payload on success for all endpoints except 'download'.
        Successful requests to the 'download' endpoint will have a return type of `bytes`.
        Throws an Exception after `self.max_api_call_retries` consecutive failures.
        """
        # Sanity check endpoint then attempt reading from cache
        loaded_from_cache = self._read_from_run_cache(endpoint=action, params=params)
        if loaded_from_cache:
            return loaded_from_cache
        # Enforce request throttling
        self._throttle()
        # Once throttling requirements are met, continue with building and submitting the request
        url = f"{RED_API_BASE_URL}?action={action}&{params}"
        json_data = self._client.get(url=url).json()
        if RED_JSON_RESPONSE_KEY not in json_data:  # pragma: no cover
            raise KeyError(f"RED response JSON missing expected '{RED_JSON_RESPONSE_KEY}' key. JSON: '{json_data}'")
        result_json = json_data[RED_JSON_RESPONSE_KEY]
        cache_write_success = self._write_cache_if_enabled(endpoint=action, params=params, result_json=result_json)
        LOGGER.debug(f"{self.__class__.__name__}: api cache write status: {cache_write_success}")
        return result_json

    def create_red_user_details(self) -> RedUserDetails:
        """
        Helper method wrapping multiple RED API calls to generate the instance of
        `plastered.models.red_models.RedUserDetails`. All the underlying calls are essentially only called in one go
        per application run to get the initial state of pre-snatched releases and ratio stats.
        """
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
