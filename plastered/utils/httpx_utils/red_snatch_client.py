import httpx

from plastered.config.config_parser import AppConfig
from plastered.run_cache.run_cache import RunCache
from plastered.utils.constants import (
    NON_CACHED_RED_SNATCH_API_ENDPOINTS,
    PERMITTED_RED_SNATCH_API_ENDPOINTS,
    RED_API_BASE_URL,
)
from plastered.utils.exceptions import RedClientSnatchException
from plastered.utils.httpx_utils.base_client import LOGGER, ThrottledAPIBaseClient


# TODO (later): refactor public `request*` methods to return Pydantic model classes.
class RedSnatchAPIClient(ThrottledAPIBaseClient):
    """
    RED client specifically for snatch requests, which have unique constraints best encapsulated in a purpose built
    class, rather than pushing into the standard RED json API client class (`RedAPIClient`).

    Also contains some specialized logic for intelligently estimating the FL tokens available.
    """

    def __init__(self, app_config: AppConfig, run_cache: RunCache):
        super().__init__(
            base_api_url=RED_API_BASE_URL,
            # NOTE: the RedSnatchAPIClient doesn't use retries, so this is ignored
            max_api_call_retries=app_config.get_cli_option("red_api_retries"),
            seconds_between_api_calls=app_config.get_cli_option("red_api_seconds_between_calls"),
            valid_endpoints=PERMITTED_RED_SNATCH_API_ENDPOINTS,
            run_cache=run_cache,
            non_cached_endpoints=NON_CACHED_RED_SNATCH_API_ENDPOINTS,
            # This class overrides the internal default super class routing, to make sure
            # there are no built-in request retries for snatching to prevent masking errors when using FL tokens.
            extra_client_transport_mount_entries={RED_API_BASE_URL: httpx.HTTPTransport()},
        )
        self._session.headers.update({"Authorization": app_config.get_cli_option("red_api_key")})
        self._available_fl_tokens = 0
        self._use_fl_tokens = app_config.get_cli_option("use_fl_tokens")
        self._tids_snatched_with_fl_tokens: set[str] = set()

    def set_initial_available_fl_tokens(self, initial_available_fl_tokens: int) -> None:
        self._available_fl_tokens = initial_available_fl_tokens
        if self._use_fl_tokens and self._available_fl_tokens == 0:
            LOGGER.warning("Currently have zero RED FL tokens available. Ignoring 'use_fl_tokens' config setting.")
            self._use_fl_tokens = False
        elif self._use_fl_tokens and self._available_fl_tokens > 0:
            LOGGER.info(f"Configured to use FL tokens. Detected {self._available_fl_tokens} FL tokens available.")
        else:
            LOGGER.warning(
                "Will not use FL tokens. To enable FL token usage, set 'search.use_fl_tokens: true' in your config.yaml file."
            )

    def snatch(self, tid: str, can_use_token: bool) -> bytes:
        """
        Dedicated method specifically for snatching from red and returning the
        response contents' bytes which may be written to a .torrent file.
        This is separated from the `request_api` method since there's addition logic for FL tokens, and since we
        don't want to enable response caching for download requests.
        """
        self._throttle()
        params = f"id={tid}"
        # Try using a FL token if the app is configured to do so and the API states a FL token is usable.
        # Fallback to non-FL download on error (i.e. out of tokens after API response, etc.)
        if self._use_fl_tokens and can_use_token and self._available_fl_tokens > 0:
            fl_snatch_failed = False
            fl_params = f"{params}&usetoken=1"
            try:
                response = self._session.get(url=f"{RED_API_BASE_URL}?action=download&{fl_params}")
                if response.is_error:
                    fl_snatch_failed = True
            except Exception:  # pragma: no cover
                fl_snatch_failed = True
            if not fl_snatch_failed:
                self._tids_snatched_with_fl_tokens.add(tid)
                self._available_fl_tokens -= 1
                LOGGER.info(
                    f"Used a FL token for tid: '{tid}'. Approximate remaining tokens: {self._available_fl_tokens}"
                )
                return response.content
            self._throttle()
        response = self._session.get(url=f"{RED_API_BASE_URL}?action=download&{params}")
        if response.is_error:
            raise RedClientSnatchException(f"Non-200 status code in response: {response.status_code}.")
        return response.content

    def tid_snatched_with_fl_token(self, tid: str | int) -> bool:
        return str(tid) in self._tids_snatched_with_fl_tokens
