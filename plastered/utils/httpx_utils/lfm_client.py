from typing import Any

from plastered.config.app_settings import AppSettings
from plastered.release_search.search_helpers import SearchItem
from plastered.utils.constants import LFM_API_BASE_URL
from plastered.utils.exceptions import LFMClientException
from plastered.utils.httpx_utils.base_client import ThrottledAPIBaseClient


# TODO (later): refactor public `request*` methods to return Pydantic model classes.
class LFMAPIClient(ThrottledAPIBaseClient):
    """
    LFM-specific Subclass of the ThrottledAPIBaseClient for interacting with the LFM API.
    Retries limit and throttling period are configured from user config.
    """

    def __init__(self, app_settings: AppSettings):
        super().__init__(
            base_api_url=LFM_API_BASE_URL,
            max_api_call_retries=app_settings.lfm.lfm_api_retries,
            seconds_between_api_calls=app_settings.lfm.lfm_api_seconds_between_calls,
        )
        self._api_key = app_settings.lfm.lfm_api_key.get_secret_value()

    def request_api(self, method: str, params: str) -> dict[str, Any]:
        """
        Helper function to hit the LFM API with retries and rate-limits.
        Returns the JSON response payload on success, and throws an Exception after max allowed consecutive failures.
        """
        # Enforce request throttling before building and submitting the request.
        self._throttle()
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
        return json_data[top_key]

    def get_album_info(self, si: SearchItem) -> dict[str, Any]:
        request_params = f"artist={si.initial_info.encoded_artist_str}&album={si.initial_info.encoded_entity_str}"
        return self.request_api(method="album.getinfo", params=request_params)

    def get_track_info(self, si: SearchItem) -> dict[str, Any]:
        request_params = f"artist={si.initial_info.encoded_artist_str}&track={si.initial_info.encoded_entity_str}"
        return self.request_api(method="track.getinfo", params=request_params)
