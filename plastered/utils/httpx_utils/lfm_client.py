from typing import Any

from plastered.config.app_settings import AppSettings
from plastered.run_cache.run_cache import RunCache
from plastered.utils.constants import LFM_API_BASE_URL, PERMITTED_LFM_API_ENDPOINTS
from plastered.utils.exceptions import LFMClientException
from plastered.utils.httpx_utils.base_client import LOGGER, ThrottledAPIBaseClient


# TODO (later): refactor public `request*` methods to return Pydantic model classes.
class LFMAPIClient(ThrottledAPIBaseClient):
    """
    LFM-specific Subclass of the ThrottledAPIBaseClient for interacting with the LFM API.
    Retries limit and throttling period are configured from user config.
    """

    def __init__(self, app_settings: AppSettings, run_cache: RunCache):
        super().__init__(
            base_api_url=LFM_API_BASE_URL,
            max_api_call_retries=app_settings.lfm.lfm_api_retries,
            seconds_between_api_calls=app_settings.lfm.lfm_api_seconds_between_calls,
            run_cache=run_cache,
            valid_endpoints=set(PERMITTED_LFM_API_ENDPOINTS),
        )
        # TODO: figure out how to redact this from logs
        self._api_key = app_settings.lfm.lfm_api_key

    def request_api(self, method: str, params: str) -> dict[str, Any]:
        """
        Helper function to hit the LFM API with retries and rate-limits.
        Returns the JSON response payload on success, and throws an Exception after max allowed consecutive failures.
        """
        # Sanity check endpoint then attempt reading from cache
        loaded_from_cache = self._read_from_run_cache(endpoint=method, params=params)
        if loaded_from_cache:
            return loaded_from_cache
        # Enforce request throttling
        self._throttle()
        # Once throttling requirements are met, continue with building and submitting the request
        lfm_response = self._client.get(
            url=f"{LFM_API_BASE_URL}?method={method}&api_key={self._api_key}&{params}&format=json",
            headers={"Accept": "application/json"},
        )
        if lfm_response.is_error:
            raise LFMClientException(
                f"Unexpected LFM API error encountered for method '{method}' and params '{params}'. Status code: {lfm_response.status_code}"
            )
        json_data = lfm_response.json()
        # LMF API does non-standard stuff with surfacing errors sometimes.
        if "error" in json_data:
            raise LFMClientException(f"LFM API error encounterd. LFM error code: '{json_data['error']}'")
        top_key = method.split(".")[0]
        result_json = json_data[top_key]
        cache_write_success = self._write_cache_if_enabled(endpoint=method, params=params, result_json=result_json)
        LOGGER.debug(f"{self.__class__.__name__}: api cache write status: {cache_write_success}")
        return result_json
