import copy
import re
from typing import Any
from unittest.mock import Mock

import httpx2
import pytest
import respx

from plastered.config.app_settings import AppSettings
from plastered.models import OriginSource
from plastered.utils.constants import PROJECT_REPO_URL
from plastered.utils.exceptions import MusicBrainzClientException, MusicBrainzRequestFailureException
from plastered.utils.http_clients.musicbrainz_client import MusicBrainzAPIClient, _select_searched_release
from plastered.version import get_project_version

_TUSS_ARID = "09292e4d-b7ad-476b-86d9-7806303ef8c3"
_OCTAGON_ARID = "3eba5e02-780b-4acd-befb-d23a0c6708dd"
_OCTAGON_RECORDING_MBID = "89f3ce2d-f83d-4a8e-9067-983bdbf691b3"


def _single_attempt_settings(app_settings: AppSettings) -> AppSettings:
    """Settings copy with a single MB API attempt, so transport-error tests don't sleep between retries."""
    mb_conf = app_settings.musicbrainz.model_copy(update={"musicbrainz_api_max_retries": 1})
    return app_settings.model_copy(update={"musicbrainz": mb_conf})


def _mb_client(app_settings: AppSettings) -> MusicBrainzAPIClient:
    mb_client = MusicBrainzAPIClient(app_settings=app_settings)
    mb_client._throttle = Mock(name="_throttle", return_value=None)
    return mb_client


@pytest.mark.override_global_httpx_mock
def test_mb_client_sends_identifying_user_agent(httpx2_mock: respx.Router, valid_app_settings: AppSettings) -> None:
    """Every MB request carries the app-identifying User-Agent MB's rate-limiting policy requires."""
    httpx2_mock.route().respond(json={"id": "x"})
    _mb_client(valid_app_settings).request_release_details(mbid="x")
    assert (
        httpx2_mock.calls[0].request.headers["user-agent"]
        == f"plastered/{get_project_version()} ( {PROJECT_REPO_URL} )"
    )


@pytest.mark.parametrize("expected_mbid", ["d211379d-3203-47ed-a0c5-e564815bb45a"])
def test_request_musicbrainz_api(valid_app_settings: AppSettings, expected_mbid: str) -> None:
    mb_client = _mb_client(valid_app_settings)
    result = mb_client.request_release_details(mbid=expected_mbid)
    mb_client._throttle.assert_called_once()
    assert isinstance(result, dict), f"Expected result from request_api to be a dict, but was: {type(result)}"
    assert "id" in result.keys(), "Missing expected top-level key in musicbrainz response: 'id'"
    response_mbid = result["id"]
    assert response_mbid == expected_mbid, (
        f"Mismatch between actual response mbid ('{response_mbid}') and expected mbid ('{expected_mbid}')"
    )


@pytest.mark.override_global_httpx_mock
def test_request_release_details_error_handling(httpx2_mock: respx.Router, valid_app_settings: AppSettings) -> None:
    httpx2_mock.route().respond(status_code=404)
    with pytest.raises(
        MusicBrainzClientException, match=re.escape("Unexpected Musicbrainz API error encountered for URL ")
    ):
        _mb_client(valid_app_settings).request_release_details(mbid="fake")


@pytest.mark.override_global_httpx_mock
def test_request_release_details_transport_error(httpx2_mock: respx.Router, valid_app_settings: AppSettings) -> None:
    """A connection/transport failure surfaces as MusicBrainzRequestFailureException, not a raw httpx2 error."""
    httpx2_mock.route().mock(
        side_effect=httpx2.ConnectError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol")
    )
    with pytest.raises(MusicBrainzRequestFailureException, match=re.escape("Musicbrainz request failed for URL ")):
        _mb_client(_single_attempt_settings(valid_app_settings)).request_release_details(mbid="fake")


@pytest.mark.override_global_httpx_mock
def test_request_release_details_invalid_json(httpx2_mock: respx.Router, valid_app_settings: AppSettings) -> None:
    """A 200 response with a non-JSON body (e.g. an HTML error page) surfaces as MusicBrainzRequestFailureException."""
    httpx2_mock.route().respond(status_code=200, text="<html>bad gateway</html>")
    with pytest.raises(MusicBrainzRequestFailureException, match=re.escape("non-JSON payload")):
        _mb_client(valid_app_settings).request_release_details(mbid="fake")


@pytest.mark.parametrize(
    "track_name, artist_name, artist_mbid, constrained, expected",
    [
        (
            "Some Track",
            "Some Artist",
            "69-420abc",
            False,
            "recording:%22Some%20Track%22%20AND%20arid:69-420abc%20AND%20NOT%20video:true",
        ),
        # Without an artist MBID the artist is matched by the combined credit OR any single credited artist's name.
        (
            "Some Track",
            "Some Artist",
            None,
            False,
            "recording:%22Some%20Track%22%20AND%20%28artist:%22Some%20Artist%22%20OR%20artistname:%22Some%20Artist%22%29"
            "%20AND%20NOT%20video:true",
        ),
        (
            "Some Track",
            "Some Artist",
            "69-420abc",
            True,
            "recording:%22Some%20Track%22%20AND%20arid:69-420abc%20AND%20NOT%20video:true%20AND%20status:official"
            "%20AND%20primarytype:album",
        ),
        # Embedded quotes must be escaped so they can't break out of the Lucene phrase term.
        (
            'Track "Quoted"',
            'Artist "Quoted"',
            None,
            False,
            "recording:%22Track%20%5C%22Quoted%5C%22%22%20AND%20%28artist:%22Artist%20%5C%22Quoted%5C%22%22%20OR%20"
            "artistname:%22Artist%20%5C%22Quoted%5C%22%22%29%20AND%20NOT%20video:true",
        ),
    ],
)
def test_mb_get_track_search_query_str(
    track_name: str, artist_name: str, artist_mbid: str | None, constrained: bool, expected: str
) -> None:
    actual = MusicBrainzAPIClient._get_track_search_query_str(
        track_name=track_name, artist_name=artist_name, artist_mbid=artist_mbid, constrained=constrained
    )
    assert actual == expected, f"Expected '{expected}', but got '{actual}'"


# ---- recording lookup -------------------------------------------------------------------------------------------


def test_lookup_recording_origin_releases_global_mock_roundtrip(
    valid_app_settings: AppSettings, mock_musicbrainz_recording_lookup_json: dict[str, Any]
) -> None:
    """The (globally mocked) recording-lookup route yields every release of the recording, in MB's order."""
    actual = _mb_client(valid_app_settings).lookup_recording_origin_releases(
        recording_mbid=_OCTAGON_RECORDING_MBID, artist_name="Dr. Octagon"
    )
    assert [c.release_mbid for c in actual] == [r["id"] for r in mock_musicbrainz_recording_lookup_json["releases"]]
    assert {c.source for c in actual} == {OriginSource.MB_RECORDING_LOOKUP}
    assert actual[0].primary_type == "Album" and actual[0].first_release_date == "1996-05-07"
    assert actual[2].primary_type == "Single"
    assert actual[3].secondary_types == ("Remix",)


@pytest.mark.override_global_httpx_mock
def test_lookup_recording_origin_releases_request_shape(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings
) -> None:
    httpx2_mock.route().respond(json={"title": "x", "artist-credit": [], "releases": []})
    assert _mb_client(valid_app_settings).lookup_recording_origin_releases(recording_mbid="abc", artist_name="A") == []
    request_url = str(httpx2_mock.calls[0].request.url)
    assert "https://musicbrainz.org/ws/2/recording/abc?inc=releases" in request_url
    assert "release-groups" in request_url and "artist-credits" in request_url and request_url.endswith("fmt=json")


def test_lookup_recording_origin_releases_artist_mismatch_returns_empty(valid_app_settings: AppSettings) -> None:
    actual = _mb_client(valid_app_settings).lookup_recording_origin_releases(
        recording_mbid=_OCTAGON_RECORDING_MBID, artist_name="Someone Else"
    )
    assert actual == []


def test_lookup_recording_origin_releases_artist_mbid_beats_name_mismatch(valid_app_settings: AppSettings) -> None:
    actual = _mb_client(valid_app_settings).lookup_recording_origin_releases(
        recording_mbid=_OCTAGON_RECORDING_MBID, artist_name="Someone Else", artist_mbid=_OCTAGON_ARID
    )
    assert len(actual) == 4


@pytest.mark.override_global_httpx_mock
def test_lookup_recording_origin_releases_error_response_returns_empty(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings
) -> None:
    """A stale recording MBID (MB answers 404) resolves to no candidates rather than an error."""
    httpx2_mock.route().respond(status_code=404)
    assert (
        _mb_client(valid_app_settings).lookup_recording_origin_releases(recording_mbid="stale", artist_name="A") == []
    )


@pytest.mark.override_global_httpx_mock
def test_lookup_recording_origin_releases_transport_error(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings
) -> None:
    httpx2_mock.route().mock(side_effect=httpx2.ConnectError("connection dropped"))
    with pytest.raises(MusicBrainzRequestFailureException, match=re.escape("Musicbrainz request failed for URL ")):
        _mb_client(_single_attempt_settings(valid_app_settings)).lookup_recording_origin_releases(
            recording_mbid="abc", artist_name="A"
        )


@pytest.mark.override_global_httpx_mock
def test_lookup_recording_origin_releases_invalid_json(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings
) -> None:
    httpx2_mock.route().respond(status_code=200, text="not json")
    with pytest.raises(MusicBrainzRequestFailureException, match=re.escape("non-JSON payload")):
        _mb_client(valid_app_settings).lookup_recording_origin_releases(recording_mbid="abc", artist_name="A")


# ---- recording search -------------------------------------------------------------------------------------------


def test_search_recording_origin_releases_by_arid_global_mock_roundtrip(valid_app_settings: AppSettings) -> None:
    """Only the recording titled like the wanted track contributes (the fixture's second recording is another track)."""
    actual = _mb_client(valid_app_settings).search_recording_origin_releases(
        track_name="1st rushup m,+3", artist_name="The Tuss", artist_mbid=_TUSS_ARID
    )
    assert [(c.release_name, c.release_mbid, c.source) for c in actual] == [
        ("Rushup Edge", "3b08749b-b63e-46d3-b693-e0736faf046f", OriginSource.MB_RECORDING_SEARCH)
    ]


def test_search_recording_origin_releases_by_artist_name_global_mock_roundtrip(
    valid_app_settings: AppSettings, mock_musicbrainz_track_search_artist_name_json: dict[str, Any]
) -> None:
    """Searching by artist name keeps only the wanted artist's recordings of the track (other artists' 'M's drop)."""
    actual = _mb_client(valid_app_settings).search_recording_origin_releases(track_name="M", artist_name="The Notwist")
    expected_release_mbids = [
        release_json["id"]
        for recording_json in mock_musicbrainz_track_search_artist_name_json["recordings"]
        if recording_json["title"] == "M" and recording_json["artist-credit"][0]["name"] == "The Notwist"
        for release_json in recording_json["releases"]
    ]
    assert expected_release_mbids, "fixture sanity: the artist-name search fixture must carry a Notwist 'M'"
    assert [c.release_mbid for c in actual] == expected_release_mbids


@pytest.mark.override_global_httpx_mock
def test_search_recording_origin_releases_constrained_then_unconstrained_retry(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings, mock_musicbrainz_track_search_arid_json: dict[str, Any]
) -> None:
    """An empty constrained (official-album) search falls back to a second, unconstrained recording search."""
    httpx2_mock.route(url__regex=r".*status:official.*").respond(json={"recordings": []})
    httpx2_mock.route(url__regex=r".*recording.*").respond(json=mock_musicbrainz_track_search_arid_json)
    actual = _mb_client(valid_app_settings).search_recording_origin_releases(
        track_name="1st rushup m,+3", artist_name="The Tuss", artist_mbid=_TUSS_ARID
    )
    assert [c.release_name for c in actual] == ["Rushup Edge"]
    assert len(httpx2_mock.calls) == 2
    first_url, second_url = str(httpx2_mock.calls[0].request.url), str(httpx2_mock.calls[1].request.url)
    assert "status:official" in first_url and "primarytype:album" in first_url
    assert "status:official" not in second_url


@pytest.mark.override_global_httpx_mock
def test_search_recording_origin_releases_request_shape(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings
) -> None:
    """Each recording search asks for MB's maximum result page and excludes video recordings."""
    httpx2_mock.route().respond(json={"recordings": []})
    assert _mb_client(valid_app_settings).search_recording_origin_releases(track_name="T", artist_name="A") == []
    assert len(httpx2_mock.calls) == 2
    for call in httpx2_mock.calls:
        request_url = str(call.request.url)
        assert "https://musicbrainz.org/ws/2/recording?query=recording:%22T%22" in request_url
        assert "NOT%20video:true" in request_url and request_url.endswith("&limit=100&fmt=json")


@pytest.mark.override_global_httpx_mock
def test_search_recording_origin_releases_stripped_title_fallback(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings, mock_musicbrainz_track_search_arid_json: dict[str, Any]
) -> None:
    """
    When neither full-title search matches, a third unconstrained search uses the title stripped of its trailing
    decorations; its recordings still pass the lenient title check against the full track name.
    """
    httpx2_mock.route(url__regex=r".*Live.*").respond(json={"recordings": []})
    httpx2_mock.route(url__regex=r".*recording.*").respond(json=mock_musicbrainz_track_search_arid_json)
    actual = _mb_client(valid_app_settings).search_recording_origin_releases(
        track_name="1st rushup m,+3 (Live) - 2011 Remaster", artist_name="The Tuss", artist_mbid=_TUSS_ARID
    )
    assert [c.release_name for c in actual] == ["Rushup Edge"]
    assert len(httpx2_mock.calls) == 3
    third_url = str(httpx2_mock.calls[2].request.url)
    assert "recording:%221st%20rushup%20m%2C%2B3%22" in third_url
    assert "Live" not in third_url and "Remaster" not in third_url and "status:official" not in third_url


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize(
    "featured_segment, featured_credit_name, expected_release_names",
    [
        ("Someone", "Someone", ["Rushup Edge"]),  # the recording credits the featured artist: accepted
        ("Someone", "Someone Else", []),  # the artist's same-titled recording without that credit: rejected
        ("Chase & Status", "Chase & Status", ["Rushup Edge"]),  # a featured band credited under its full name
        ("Someone & Chase", "Chase", ["Rushup Edge"]),  # one of several featured artists credited
    ],
)
def test_search_recording_origin_releases_stripped_feat_requires_featured_credit(
    httpx2_mock: respx.Router,
    valid_app_settings: AppSettings,
    mock_musicbrainz_track_search_arid_json: dict[str, Any],
    featured_segment: str,
    featured_credit_name: str,
    expected_release_names: list[str],
) -> None:
    """A stripped "(feat. X)" pass only accepts recordings whose artist credit names X."""
    search_json = copy.deepcopy(mock_musicbrainz_track_search_arid_json)
    search_json["recordings"][0]["artist-credit"][0]["joinphrase"] = " feat. "
    search_json["recordings"][0]["artist-credit"].append(
        {"name": featured_credit_name, "artist": {"id": "feat-arid", "name": featured_credit_name}}
    )
    httpx2_mock.route(url__regex=r".*feat.*").respond(json={"recordings": []})
    httpx2_mock.route(url__regex=r".*recording.*").respond(json=search_json)
    actual = _mb_client(valid_app_settings).search_recording_origin_releases(
        track_name=f"1st rushup m,+3 (feat. {featured_segment})", artist_name="The Tuss", artist_mbid=_TUSS_ARID
    )
    assert [c.release_name for c in actual] == expected_release_names
    assert len(httpx2_mock.calls) == 3


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize(
    "track_name, expected_call_count",
    [
        ("Some Other Track", 2),  # no trailing decoration: nothing to strip, no third search
        ("Some Other Track (Live)", 3),
        ("(Untitled)", 2),  # stripping would leave nothing: the title stands, no third search
        ("(Nice Dream) - Remastered", 3),  # the bracketed core survives, so the suffix strip earns a third search
    ],
)
def test_search_recording_origin_releases_search_pass_count(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings, track_name: str, expected_call_count: int
) -> None:
    httpx2_mock.route().respond(json={"recordings": []})
    actual = _mb_client(valid_app_settings).search_recording_origin_releases(
        track_name=track_name, artist_name="The Tuss", artist_mbid=_TUSS_ARID
    )
    assert actual == []
    assert len(httpx2_mock.calls) == expected_call_count


@pytest.mark.override_global_httpx_mock
def test_search_recording_origin_releases_title_mismatch_returns_empty(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings, mock_musicbrainz_track_search_arid_json: dict[str, Any]
) -> None:
    httpx2_mock.route().respond(json=mock_musicbrainz_track_search_arid_json)
    actual = _mb_client(valid_app_settings).search_recording_origin_releases(
        track_name="Some Other Track", artist_name="The Tuss", artist_mbid=_TUSS_ARID
    )
    assert actual == []
    assert len(httpx2_mock.calls) == 2


@pytest.mark.override_global_httpx_mock
def test_search_recording_origin_releases_untitled_releases_yield_nothing(
    httpx2_mock: respx.Router,
    valid_app_settings: AppSettings,
    mock_musicbrainz_track_search_no_release_name_json: dict[str, Any],
) -> None:
    httpx2_mock.route().respond(json=mock_musicbrainz_track_search_no_release_name_json)
    actual = _mb_client(valid_app_settings).search_recording_origin_releases(
        track_name="1st rushup m,+3", artist_name="The Tuss"
    )
    assert actual == []


@pytest.mark.override_global_httpx_mock
def test_search_recording_origin_releases_error_response_returns_empty(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings
) -> None:
    httpx2_mock.route().respond(status_code=503)
    assert _mb_client(valid_app_settings).search_recording_origin_releases(track_name="T", artist_name="A") == []
    assert len(httpx2_mock.calls) == 1


@pytest.mark.override_global_httpx_mock
def test_search_recording_origin_releases_transport_error(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings
) -> None:
    httpx2_mock.route().mock(side_effect=httpx2.ConnectError("connection dropped"))
    with pytest.raises(MusicBrainzRequestFailureException, match=re.escape("Musicbrainz request failed for URL ")):
        _mb_client(_single_attempt_settings(valid_app_settings)).search_recording_origin_releases(
            track_name="T", artist_name="A"
        )


@pytest.mark.override_global_httpx_mock
def test_search_recording_origin_releases_invalid_json(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings
) -> None:
    httpx2_mock.route().respond(status_code=200, text="not json")
    with pytest.raises(MusicBrainzRequestFailureException, match=re.escape("non-JSON payload")):
        _mb_client(valid_app_settings).search_recording_origin_releases(track_name="T", artist_name="A")


# ---- release search ---------------------------------------------------------------------------------------------


def test_search_release_mbid_returns_album_result(valid_app_settings: AppSettings) -> None:
    """The (globally mocked) release-search route resolves the top-scored Album release's MBID."""
    actual = _mb_client(valid_app_settings).search_release_mbid(
        artist_name="Dr. Octagon", release_name="Dr. Octagonecologyst"
    )
    assert actual == "d211379d-3203-47ed-a0c5-e564815bb45a"


@pytest.mark.override_global_httpx_mock
def test_search_release_mbid_query_shape(httpx2_mock: respx.Router, valid_app_settings: AppSettings) -> None:
    httpx2_mock.route().respond(json={"releases": [{"id": "some-mbid"}]})
    assert (
        _mb_client(valid_app_settings).search_release_mbid(artist_name="Some Artist", release_name="Some Album")
        == "some-mbid"
    )
    assert len(httpx2_mock.calls) == 1
    request_url = str(httpx2_mock.calls[0].request.url)
    assert (
        "release?query=release:%22Some%20Album%22%20AND%20artist:%22Some%20Artist%22%20AND%20status:official"
        in request_url
    )
    assert request_url.endswith("&limit=5&fmt=json")


@pytest.mark.override_global_httpx_mock
def test_search_release_mbid_retries_without_status_constraint(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings
) -> None:
    """When no official release matches, the search is retried without the status constraint."""
    httpx2_mock.route(url__regex=r".*status:official.*").respond(json={"releases": []})
    httpx2_mock.route(url__regex=r".*release\?query=.*").respond(json={"releases": [{"id": "unofficial-mbid"}]})
    actual = _mb_client(valid_app_settings).search_release_mbid(artist_name="Some Artist", release_name="Some Album")
    assert actual == "unofficial-mbid"
    assert len(httpx2_mock.calls) == 2
    assert "status:official" not in str(httpx2_mock.calls[1].request.url)


@pytest.mark.parametrize(
    "releases, release_name, expected_id",
    [
        # Among same-titled hits an Album beats a higher-scored single.
        (
            [
                {"id": "single", "title": "Foo", "release-group": {"primary-type": "Single"}},
                {"id": "album", "title": "Foo", "release-group": {"primary-type": "Album"}},
            ],
            "Foo",
            "album",
        ),
        # A wanted EP must not resolve to a similarly named album.
        (
            [
                {"id": "ep", "title": "Foo EP", "release-group": {"primary-type": "EP"}},
                {"id": "album", "title": "Foo", "release-group": {"primary-type": "Album"}},
            ],
            "Foo EP",
            "ep",
        ),
        # Title comparison is normalized; an untyped same-titled hit loses to a same-titled Album.
        (
            [
                {"id": "untyped", "title": "Foo", "release-group": None},
                {"id": "album", "title": "foo!", "release-group": {"primary-type": "album"}},
            ],
            "Foo",
            "album",
        ),
        # No same-titled hit: the top-scored hit stands.
        (
            [
                {"id": "top", "title": "Bar"},
                {"id": "album", "title": "Baz", "release-group": {"primary-type": "Album"}},
            ],
            "Foo",
            "top",
        ),
        ([{"id": "bare"}], "Foo", "bare"),
    ],
)
def test_select_searched_release(releases: list[dict[str, Any]], release_name: str, expected_id: str) -> None:
    assert _select_searched_release(releases=releases, release_name=release_name)["id"] == expected_id


@pytest.mark.override_global_httpx_mock
@pytest.mark.parametrize("mock_json", [{"releases": []}, {}])
def test_search_release_mbid_no_results(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings, mock_json: dict[str, Any]
) -> None:
    httpx2_mock.route().respond(json=mock_json)
    assert (
        _mb_client(valid_app_settings).search_release_mbid(artist_name="Some Artist", release_name="Some Album") is None
    )
    assert len(httpx2_mock.calls) == 2


@pytest.mark.override_global_httpx_mock
def test_search_release_mbid_error_response_returns_none(
    httpx2_mock: respx.Router, valid_app_settings: AppSettings
) -> None:
    httpx2_mock.route().respond(status_code=503)
    assert (
        _mb_client(valid_app_settings).search_release_mbid(artist_name="Some Artist", release_name="Some Album") is None
    )


@pytest.mark.override_global_httpx_mock
def test_search_release_mbid_transport_error(httpx2_mock: respx.Router, valid_app_settings: AppSettings) -> None:
    httpx2_mock.route().mock(side_effect=httpx2.ConnectError("connection dropped"))
    with pytest.raises(MusicBrainzRequestFailureException, match=re.escape("Musicbrainz request failed for URL ")):
        _mb_client(_single_attempt_settings(valid_app_settings)).search_release_mbid(
            artist_name="Some Artist", release_name="Some Album"
        )


@pytest.mark.override_global_httpx_mock
def test_search_release_mbid_invalid_json(httpx2_mock: respx.Router, valid_app_settings: AppSettings) -> None:
    httpx2_mock.route().respond(status_code=200, text="not json")
    with pytest.raises(MusicBrainzRequestFailureException, match=re.escape("non-JSON payload")):
        _mb_client(valid_app_settings).search_release_mbid(artist_name="Some Artist", release_name="Some Album")
