import re
from typing import Any
from unittest.mock import Mock

import httpx2
import pytest
import respx

from plastered.config.app_settings import AppSettings
from plastered.utils.exceptions import MusicBrainzClientException, MusicBrainzRequestFailureException
from plastered.utils.http_clients.musicbrainz_client import MusicBrainzAPIClient


def _single_attempt_settings(app_settings: AppSettings) -> AppSettings:
    """Settings copy with a single MB API attempt, so transport-error tests don't sleep between retries."""
    mb_conf = app_settings.musicbrainz.model_copy(update={"musicbrainz_api_max_retries": 1})
    return app_settings.model_copy(update={"musicbrainz": mb_conf})


@pytest.fixture(scope="session")
def mb_track_response_raise_index_error() -> dict[str, Any]:
    return {"recordings": []}


@pytest.fixture(scope="session")
def mb_track_response_raise_key_error() -> dict[str, Any]:
    return {"recordings": [{"missing_releases_key": True}]}


@pytest.mark.parametrize("expected_mbid", ["d211379d-3203-47ed-a0c5-e564815bb45a"])
def test_request_musicbrainz_api(valid_app_settings: AppSettings, expected_mbid: str) -> None:
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle")
    mb_client._throttle.return_value = None
    result = mb_client.request_release_details(mbid=expected_mbid)
    mb_client._throttle.assert_called_once()
    assert isinstance(result, dict), f"Expected result from request_api to be a dict, but was: {type(result)}"
    assert "id" in result.keys(), "Missing expected top-level key in musicbrainz response: 'id'"
    response_mbid = result["id"]
    assert response_mbid == expected_mbid, (
        f"Mismatch between actual response mbid ('{response_mbid}') and expected mbid ('{expected_mbid}')"
    )


@pytest.mark.parametrize(
    "track_name, artist_mbid, artist_name, constrained, expected",
    [
        ("Some Track", "69-420abc", "Some Artist", False, "recording:%22Some%20Track%22%20AND%20arid:69-420abc"),
        ("Some Track", None, "Some Artist", False, "recording:%22Some%20Track%22%20AND%20artist:%22Some%20Artist%22"),
        (
            "Some Track",
            "69-420abc",
            "Some Artist",
            True,
            "recording:%22Some%20Track%22%20AND%20arid:69-420abc%20AND%20status:official%20AND%20primarytype:album",
        ),
        # Embedded quotes must be escaped so they can't break out of the Lucene phrase term.
        (
            'Track "Quoted"',
            "69-420abc",
            None,
            False,
            "recording:%22Track%20%5C%22Quoted%5C%22%22%20AND%20arid:69-420abc",
        ),
        ("Some Track", None, None, False, None),
    ],
)
def test_mb_get_track_search_query_str(
    valid_app_settings: AppSettings,
    track_name: str,
    artist_mbid: str | None,
    artist_name: str | None,
    constrained: bool,
    expected: str | None,
) -> None:
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle")
    mb_client._throttle.return_value = None
    actual = mb_client._get_track_search_query_str(
        human_readable_track_name=track_name,
        artist_mbid=artist_mbid,
        human_readable_artist_name=artist_name,
        constrained=constrained,
    )
    assert actual == expected, f"Expected '{expected}', but got '{actual}'"


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize("is_lfm_rec", [False, True])
@pytest.mark.parametrize(
    "mock_mb_json_response_fixture_name, track_name, artist_mbid, artist_name, expected",
    [
        (  # test case 1
            "mock_musicbrainz_track_search_arid_json",
            "rushup i bank 12 M",
            "09292e4d-b7ad-476b-86d9-7806303ef8c3",
            "The Tuss",
            {"origin_release_mbid": "3b08749b-b63e-46d3-b693-e0736faf046f", "origin_release_name": "Rushup Edge"},
        ),
        (  # test case 2: full track info provided
            "mock_musicbrainz_track_search_arid_json",
            "rushup i bank 12 M",
            "09292e4d-b7ad-476b-86d9-7806303ef8c3",
            "The Tuss",
            {"origin_release_mbid": "3b08749b-b63e-46d3-b693-e0736faf046f", "origin_release_name": "Rushup Edge"},
        ),
        (  # test case 3: result from searching by artist name and not arid.
            "mock_musicbrainz_track_search_artist_name_json",
            "rushup i bank 12 M",
            None,
            "The Tuss",
            {"origin_release_mbid": "3b08749b-b63e-46d3-b693-e0736faf046f", "origin_release_name": "Rushup Edge"},
        ),
        (  # test case 4: mbid response has no release title in it, should return None
            "mock_musicbrainz_track_search_no_release_name_json",
            "rushup i bank 12 M",
            None,
            "The Tuss",
            None,
        ),
        (  # test case 5: json response triggers a KeyError, result should be None
            "mb_track_response_raise_key_error",
            "rushup i bank 12 M",
            "09292e4d-b7ad-476b-86d9-7806303ef8c3",
            "The Tuss",
            None,
        ),
        (  # test case 6: json response triggers an IndexError, result should be None
            "mb_track_response_raise_index_error",
            "rushup i bank 12 M",
            "09292e4d-b7ad-476b-86d9-7806303ef8c3",
            "The Tuss",
            None,
        ),
    ],
)
def test_request_release_details_for_track(
    httpx2_mock: respx.Router,
    request: pytest.FixtureRequest,
    valid_app_settings: AppSettings,
    make_track_search_item: pytest.FixtureRequest,
    is_lfm_rec: bool,
    mock_mb_json_response_fixture_name: str,
    track_name: str,
    artist_mbid: str | None,
    artist_name: str,
    expected: dict[str, str | None] | None,
) -> None:
    mock_json_resp = request.getfixturevalue(mock_mb_json_response_fixture_name)
    httpx2_mock.route().respond(json=mock_json_resp)
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle")
    mb_client._throttle.return_value = None
    mock_si = make_track_search_item(is_lfm_rec=is_lfm_rec, artist=artist_name, track=track_name)
    actual = mb_client.request_release_details_for_track(si=mock_si, artist_mbid=artist_mbid)
    assert actual == expected, f"Expected {expected}, but got {actual}"


@pytest.mark.override_global_httpx_mock
def test_request_release_details_error_handling(httpx2_mock: respx.Router, valid_app_settings: AppSettings) -> None:
    httpx2_mock.route().respond(status_code=404)
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle")
    mb_client._throttle.return_value = None
    with pytest.raises(
        MusicBrainzClientException, match=re.escape("Unexpected Musicbrainz API error encountered for URL ")
    ):
        mb_client.request_release_details(mbid="fake")


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize("is_lfm_rec", [False, True])
def test_request_release_details_for_track_error_handling(
    httpx2_mock: respx.Router,
    valid_app_settings: AppSettings,
    make_track_search_item: pytest.FixtureRequest,
    is_lfm_rec: bool,
) -> None:
    httpx2_mock.route().respond(status_code=404)
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle")
    mb_client._throttle.return_value = None
    mock_si = make_track_search_item(is_lfm_rec=is_lfm_rec)
    actual = mb_client.request_release_details_for_track(si=mock_si, artist_mbid="a")
    assert actual is None


@pytest.mark.override_global_httpx_mock
def test_request_release_details_transport_error(httpx2_mock: respx.Router, valid_app_settings: AppSettings) -> None:
    """A connection/transport failure surfaces as MusicBrainzRequestFailureException, not a raw httpx2 error."""
    httpx2_mock.route().mock(
        side_effect=httpx2.ConnectError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol")
    )
    mb_client = MusicBrainzAPIClient(app_settings=_single_attempt_settings(valid_app_settings))
    mb_client._throttle = Mock(name="_throttle", return_value=None)
    with pytest.raises(MusicBrainzRequestFailureException, match=re.escape("Musicbrainz request failed for URL ")):
        mb_client.request_release_details(mbid="fake")


@pytest.mark.override_global_httpx_mock
def test_request_release_details_invalid_json(httpx2_mock: respx.Router, valid_app_settings: AppSettings) -> None:
    """A 200 response with a non-JSON body (e.g. an HTML error page) surfaces as MusicBrainzRequestFailureException."""
    httpx2_mock.route().respond(status_code=200, text="<html>bad gateway</html>")
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle", return_value=None)
    with pytest.raises(MusicBrainzRequestFailureException, match=re.escape("non-JSON payload")):
        mb_client.request_release_details(mbid="fake")


@pytest.mark.override_global_httpx_mock
def test_request_release_details_for_track_transport_error(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings, make_track_search_item: pytest.FixtureRequest
) -> None:
    """A connection/transport failure during track origin-release resolution raises the request-failure exception."""
    httpx2_mock.route().mock(side_effect=httpx2.ConnectError("connection dropped"))
    mb_client = MusicBrainzAPIClient(app_settings=_single_attempt_settings(valid_app_settings))
    mb_client._throttle = Mock(name="_throttle", return_value=None)
    mock_si = make_track_search_item(is_lfm_rec=True)
    with pytest.raises(MusicBrainzRequestFailureException, match=re.escape("Musicbrainz request failed for URL ")):
        mb_client.request_release_details_for_track(si=mock_si, artist_mbid="a")


@pytest.mark.override_global_httpx_mock
def test_request_release_details_for_track_invalid_json(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings, make_track_search_item: pytest.FixtureRequest
) -> None:
    """A 200 response with a non-JSON body during track origin-release resolution raises the request-failure exception."""
    httpx2_mock.route().respond(status_code=200, text="not json")
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle", return_value=None)
    mock_si = make_track_search_item(is_lfm_rec=True)
    with pytest.raises(MusicBrainzRequestFailureException, match=re.escape("non-JSON payload")):
        mb_client.request_release_details_for_track(si=mock_si, artist_mbid="a")


@pytest.mark.override_global_httpx_mock
def test_request_release_details_for_track_constrained_then_unconstrained_retry(
    httpx2_mock: respx.Router,
    valid_app_settings: AppSettings,
    make_track_search_item: pytest.FixtureRequest,
    mock_musicbrainz_track_search_arid_json: dict[str, Any],
) -> None:
    """An empty constrained (official-album) search falls back to a second, unconstrained recording search."""
    httpx2_mock.route(url__regex=r".*status:official.*").respond(json={"recordings": []})
    httpx2_mock.route(url__regex=r".*recording.*").respond(json=mock_musicbrainz_track_search_arid_json)
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle", return_value=None)
    mock_si = make_track_search_item(is_lfm_rec=True)
    actual = mb_client.request_release_details_for_track(si=mock_si, artist_mbid="a")
    assert actual == {
        "origin_release_mbid": "3b08749b-b63e-46d3-b693-e0736faf046f",
        "origin_release_name": "Rushup Edge",
    }
    assert len(httpx2_mock.calls) == 2
    first_url, second_url = str(httpx2_mock.calls[0].request.url), str(httpx2_mock.calls[1].request.url)
    assert "status:official" in first_url and "primarytype:album" in first_url
    assert "status:official" not in second_url


@pytest.mark.override_global_httpx_mock
def test_request_release_details_for_track_prefers_earliest_official_album(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings, make_track_search_item: pytest.FixtureRequest
) -> None:
    """Among a recording's releases, the earliest-dated official Album release wins over promos/compilations."""
    mock_json = {
        "recordings": [
            {
                "title": "Some Track",
                "releases": [
                    {"id": "promo", "title": "Promo Comp", "status": "Promotion", "date": "1995"},
                    {
                        "id": "reissue",
                        "title": "Origin Album",
                        "status": "Official",
                        "date": "2005-01-01",
                        "release-group": {"primary-type": "Album"},
                    },
                    {
                        "id": "original",
                        "title": "Origin Album",
                        "status": "Official",
                        "date": "1997-09-29",
                        "release-group": {"primary-type": "Album"},
                    },
                    {
                        "id": "undated",
                        "title": "Origin Album",
                        "status": "Official",
                        "release-group": {"primary-type": "Album"},
                    },
                ],
            }
        ]
    }
    httpx2_mock.route().respond(json=mock_json)
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle", return_value=None)
    mock_si = make_track_search_item(is_lfm_rec=True)
    actual = mb_client.request_release_details_for_track(si=mock_si, artist_mbid="a")
    assert actual == {"origin_release_mbid": "original", "origin_release_name": "Origin Album"}


@pytest.mark.override_global_httpx_mock
def test_request_release_details_for_track_falls_back_to_first_release(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings, make_track_search_item: pytest.FixtureRequest
) -> None:
    """With no official Album release anywhere, the first release of the first recording is used."""
    mock_json = {
        "recordings": [
            {"title": "Some Track", "releases": [{"id": "single", "title": "Some Single", "status": "Official"}]}
        ]
    }
    httpx2_mock.route().respond(json=mock_json)
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle", return_value=None)
    mock_si = make_track_search_item(is_lfm_rec=True)
    actual = mb_client.request_release_details_for_track(si=mock_si, artist_mbid="a")
    assert actual == {"origin_release_mbid": "single", "origin_release_name": "Some Single"}


@pytest.mark.parametrize("is_lfm_rec", [False, True])
def test_request_release_details_for_track_global_mock_roundtrip(
    valid_app_settings: AppSettings, make_track_search_item: pytest.FixtureRequest, is_lfm_rec: bool
) -> None:
    """The default (globally mocked) recording-search routes resolve the origin release end-to-end."""
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle", return_value=None)
    mock_si = make_track_search_item(is_lfm_rec=is_lfm_rec, artist="The Tuss", track="rushup i bank 12 M")
    actual = mb_client.request_release_details_for_track(si=mock_si)
    assert actual == {
        "origin_release_mbid": "3b08749b-b63e-46d3-b693-e0736faf046f",
        "origin_release_name": "Rushup Edge",
    }


def test_search_release_mbid_returns_top_result(valid_app_settings: AppSettings) -> None:
    """The (globally mocked) release-search route resolves the top-scored release's MBID."""
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle", return_value=None)
    actual = mb_client.search_release_mbid(artist_name="Dr. Octagon", release_name="Dr. Octagonecologyst")
    assert actual == "d211379d-3203-47ed-a0c5-e564815bb45a"


@pytest.mark.override_global_httpx_mock
def test_search_release_mbid_query_shape(httpx2_mock: respx.Router, valid_app_settings: AppSettings) -> None:
    httpx2_mock.route().respond(json={"releases": [{"id": "some-mbid"}]})
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle", return_value=None)
    assert mb_client.search_release_mbid(artist_name="Some Artist", release_name="Some Album") == "some-mbid"
    request_url = str(httpx2_mock.calls[0].request.url)
    assert "release?query=release:%22Some%20Album%22%20AND%20artist:%22Some%20Artist%22" in request_url
    assert request_url.endswith("&limit=5&fmt=json")


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize("mock_json", [{"releases": []}, {}])
def test_search_release_mbid_no_results(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings, mock_json: dict[str, Any]
) -> None:
    httpx2_mock.route().respond(json=mock_json)
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle", return_value=None)
    assert mb_client.search_release_mbid(artist_name="Some Artist", release_name="Some Album") is None


@pytest.mark.override_global_httpx_mock
def test_search_release_mbid_error_response_returns_none(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings
) -> None:
    httpx2_mock.route().respond(status_code=503)
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle", return_value=None)
    assert mb_client.search_release_mbid(artist_name="Some Artist", release_name="Some Album") is None


@pytest.mark.override_global_httpx_mock
def test_search_release_mbid_transport_error(httpx2_mock: respx.Router, valid_app_settings: AppSettings) -> None:
    httpx2_mock.route().mock(side_effect=httpx2.ConnectError("connection dropped"))
    mb_client = MusicBrainzAPIClient(app_settings=_single_attempt_settings(valid_app_settings))
    mb_client._throttle = Mock(name="_throttle", return_value=None)
    with pytest.raises(MusicBrainzRequestFailureException, match=re.escape("Musicbrainz request failed for URL ")):
        mb_client.search_release_mbid(artist_name="Some Artist", release_name="Some Album")


@pytest.mark.override_global_httpx_mock
def test_search_release_mbid_invalid_json(httpx2_mock: respx.Router, valid_app_settings: AppSettings) -> None:
    httpx2_mock.route().respond(status_code=200, text="not json")
    mb_client = MusicBrainzAPIClient(app_settings=valid_app_settings)
    mb_client._throttle = Mock(name="_throttle", return_value=None)
    with pytest.raises(MusicBrainzRequestFailureException, match=re.escape("non-JSON payload")):
        mb_client.search_release_mbid(artist_name="Some Artist", release_name="Some Album")
