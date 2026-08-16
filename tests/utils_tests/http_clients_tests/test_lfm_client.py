from contextlib import nullcontext
from unittest.mock import Mock, patch

import httpx2
import pytest
import respx

from plastered.config.app_settings import AppSettings
from plastered.models.search_item import SearchItem
from plastered.utils.exceptions import LFMClientException, LFMRequestFailureException
from plastered.utils.http_clients import LFMAPIClient


def _single_attempt_settings(app_settings: AppSettings) -> AppSettings:
    """Settings copy with a single LFM API attempt, so transport-error tests don't sleep between retries."""
    lfm_conf = app_settings.lfm.model_copy(update={"lfm_api_retries": 1})
    return app_settings.model_copy(update={"lfm": lfm_conf})


@pytest.fixture(scope="session")
def expected_lfm_request_api_res_top_keys() -> dict[str, set[str]]:
    """
    Utility fixture which maps an LFM API endpoint to the expected set of top-level keys
    returned by the lfm_client.request_api call.
    """
    return {
        "album.getinfo": set(
            ["artist", "image", "listeners", "mbid", "name", "playcount", "tags", "tracks", "url", "wiki"]
        ),
        "track.getinfo": set(
            ["album", "artist", "duration", "listeners", "mbid", "name", "playcount", "streamable", "toptags", "url"]
        ),
    }


@pytest.mark.parametrize("method", ["album.getinfo", "track.getinfo"])
def test_request_lfm_api(
    valid_app_settings: AppSettings, expected_lfm_request_api_res_top_keys: dict[str, set[str]], method: str
) -> None:
    lfm_client = LFMAPIClient(app_settings=valid_app_settings)
    lfm_client._throttle = Mock(name="_throttle")
    lfm_client._throttle.return_value = None
    result = lfm_client.request_api(method=method, params="fakekey=fakevalue")
    lfm_client._throttle.assert_called_once()
    assert isinstance(result, dict), f"Expected request_lfm_api result type of dict, but found: {type(result)}"
    assert set(result.keys()) == expected_lfm_request_api_res_top_keys[method]


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize("method", ["album.getinfo", "track.getinfo"])
def test_request_lfm_api_non_200_status(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings, method: str
) -> None:
    httpx2_mock.route().respond(status_code=404)
    lfm_client = LFMAPIClient(app_settings=valid_app_settings)
    lfm_client._throttle = Mock(name="_throttle")
    lfm_client._throttle.return_value = None
    with pytest.raises(LFMClientException, match=f"Unexpected LFM API error encountered for method '{method}'"):
        result = lfm_client.request_api(method=method, params="fakekey=fakevalue")
        lfm_client._throttle.assert_called_once()


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize("method", ["album.getinfo", "track.getinfo"])
def test_request_lfm_api_bad_json_response(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings, method: str
) -> None:
    httpx2_mock.route().respond(
        status_code=200, json={"error": 123, "message": "LFM API handles errors like this sometimes"}
    )
    lfm_client = LFMAPIClient(app_settings=valid_app_settings)
    lfm_client._throttle = Mock(name="_throttle")
    lfm_client._throttle.return_value = None
    with pytest.raises(LFMClientException, match="LFM API error encounterd. LFM error code: '123'"):
        lfm_client.request_api(method=method, params="fakekey=fakevalue")


@pytest.mark.override_global_httpx_mock
def test_request_lfm_api_transport_error(httpx2_mock: respx.Router, valid_app_settings: AppSettings) -> None:
    """A connection/transport failure surfaces as LFMRequestFailureException, not a raw httpx2 error."""
    httpx2_mock.route().mock(side_effect=httpx2.ConnectError("connection dropped"))
    lfm_client = LFMAPIClient(app_settings=_single_attempt_settings(valid_app_settings))
    lfm_client._throttle = Mock(name="_throttle", return_value=None)
    with pytest.raises(LFMRequestFailureException, match="LFM request failed for method 'album.getinfo'"):
        lfm_client.request_api(method="album.getinfo", params="fakekey=fakevalue")


@pytest.mark.override_global_httpx_mock
def test_request_lfm_api_non_json_payload(httpx2_mock: respx.Router, valid_app_settings: AppSettings) -> None:
    """A 200 response with a non-JSON body (e.g. an HTML error page) surfaces as LFMRequestFailureException."""
    httpx2_mock.route().respond(status_code=200, text="<html>bad gateway</html>")
    lfm_client = LFMAPIClient(app_settings=valid_app_settings)
    lfm_client._throttle = Mock(name="_throttle", return_value=None)
    with pytest.raises(LFMRequestFailureException, match="non-JSON payload"):
        lfm_client.request_api(method="album.getinfo", params="fakekey=fakevalue")


@pytest.mark.parametrize("is_lfm_rec", [False, True])
def test_get_album_info(
    valid_app_settings: AppSettings, make_album_search_item: pytest.FixtureRequest, is_lfm_rec: bool
) -> None:
    mock_si: SearchItem = make_album_search_item(is_lfm_rec=is_lfm_rec)
    expected_req_params = (
        f"artist={mock_si.initial_info.encoded_artist_str}&album={mock_si.initial_info.encoded_entity_str}"
    )
    with patch.object(LFMAPIClient, "request_api", return_value=dict()) as mock_request_api:
        test_client = LFMAPIClient(app_settings=valid_app_settings)
        actual = test_client.get_album_info(si=mock_si)
        assert isinstance(actual, dict)
        mock_request_api.assert_called_once_with(method="album.getinfo", params=expected_req_params)


@pytest.mark.parametrize("is_lfm_rec", [False, True])
def test_get_track_info(
    valid_app_settings: AppSettings, make_track_search_item: pytest.FixtureRequest, is_lfm_rec: bool
) -> None:
    mock_si: SearchItem = make_track_search_item(is_lfm_rec=is_lfm_rec)
    expected_req_params = (
        f"artist={mock_si.initial_info.encoded_artist_str}&track={mock_si.initial_info.encoded_entity_str}"
    )
    with patch.object(LFMAPIClient, "request_api", return_value=dict()) as mock_request_api:
        test_client = LFMAPIClient(app_settings=valid_app_settings)
        actual = test_client.get_track_info(si=mock_si)
        assert isinstance(actual, dict)
        mock_request_api.assert_called_once_with(method="track.getinfo", params=expected_req_params)
