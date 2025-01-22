import os
from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple
from unittest.mock import Mock, call, patch

import pytest

from plastered.config.config_parser import AppConfig
from plastered.release_search.release_searcher import (
    ReleaseSearcher,
    require_mbid_resolution,
)
from plastered.scraper.lfm_scraper import LFMRec, RecContext, RecommendationType
from plastered.stats.stats import SkippedReason, SnatchFailureReason
from plastered.utils.exceptions import (
    RedClientSnatchException,
    ReleaseSearcherException,
)
from plastered.utils.http_utils import LFMAPIClient, MusicBrainzAPIClient, RedAPIClient
from plastered.utils.lfm_utils import LFMAlbumInfo, LFMTrackInfo
from plastered.utils.musicbrainz_utils import MBRelease
from plastered.utils.red_utils import (
    EncodingEnum,
    FormatEnum,
    MediaEnum,
    RedFormat,
    RedReleaseType,
    RedUserDetails,
    TorrentEntry,
)
from tests.conftest import (
    mock_full_lfm_track_info_json,
    mock_lfm_album_info_json,
    mock_lfm_session_get_side_effect,
    mock_lfm_track_info_raise_client_exception,
    mock_mb_session_get_side_effect,
    mock_musicbrainz_track_search_arid_json,
    mock_musicbrainz_track_search_artist_name_json,
    mock_no_album_lfm_track_info_json,
    mock_red_browse_non_empty_response,
    mock_red_session_get_side_effect,
    mock_red_user_details,
    mock_red_user_stats_response,
    mock_red_user_torrents_snatched_response,
    valid_app_config,
)

_EXPECTED_TSV_OUTPUT_HEADER = "entity_type\trec_context\tlfm_entity_url\tred_permalink\trelease_mbid\n"


@pytest.fixture(scope="session")
def mock_lfmai() -> LFMAlbumInfo:
    return LFMAlbumInfo(artist="Foo", release_mbid="1234", album_name="Bar", lfm_url="https://blah.com")


@pytest.fixture(scope="function")
def mock_lfm_track_info() -> LFMTrackInfo:
    return LFMTrackInfo("Some Artist", "Track Title", "Source Album", "https://fake-url", "69-420")


@pytest.fixture(scope="function")
def no_snatch_user_details() -> RedUserDetails:
    return RedUserDetails(user_id=12345, snatched_count=0, snatched_torrents_list=[])


@pytest.fixture(scope="session")
def mock_mbr() -> MBRelease:
    return MBRelease(
        mbid="1234",
        title="Bar",
        artist="Foo",
        primary_type="Album",
        release_date="2017-05-19",
        first_release_year=2016,
        label="Get On Down",
        catalog_number="58010",
        release_group_mbid="b38e21f6-8f76-3f87-a021-e91afad9e7e5",
    )


@pytest.fixture(scope="function")
def mock_best_te() -> TorrentEntry:
    return TorrentEntry(
        torrent_id=69420,
        media="WEB",
        format="FLAC",
        encoding="24bit Lossless",
        size=69420,
        scene=False,
        trumpable=False,
        has_snatched=False,
        has_log=False,
        log_score=0,
        has_cue=False,
        can_use_token=False,
        reported=None,
        lossy_web=None,
        lossy_master=None,
    )


@pytest.mark.parametrize(
    "red_format, release_type, first_release_year, record_label, catalog_number, expected_browse_params",
    [
        (
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
            None,
            None,
            None,
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc",
        ),
        (
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.LOSSLESS, media=MediaEnum.WEB),
            None,
            None,
            None,
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc",
        ),
        (
            RedFormat(format=FormatEnum.MP3, encoding=EncodingEnum.MP3_V0, media=MediaEnum.WEB),
            None,
            None,
            None,
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=MP3&encoding=V0+(VBR)&media=WEB&group_results=1&order_by=seeders&order_way=desc",
        ),
        (
            RedFormat(format=FormatEnum.MP3, encoding=EncodingEnum.MP3_V0, media=MediaEnum.CD),
            None,
            None,
            None,
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=MP3&encoding=V0+(VBR)&media=CD&group_results=1&order_by=seeders&order_way=desc",
        ),
        (
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
            RedReleaseType.ALBUM,
            None,
            None,
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc&releasetype=1",
        ),
        (
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
            None,
            1969,
            None,
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc&year=1969",
        ),
        (
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
            None,
            None,
            "Fake Label",
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc&recordlabel=Fake+Label",
        ),
        (
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
            None,
            None,
            None,
            "FL 69420",
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc&cataloguenumber=FL+69420",
        ),
    ],
)
def test_create_browse_params(
    valid_app_config: AppConfig,
    red_format: RedFormat,
    release_type: Optional[RedReleaseType],
    first_release_year: Optional[int],
    record_label: Optional[str],
    catalog_number: Optional[str],
    expected_browse_params: str,
) -> None:
    release_searcher = ReleaseSearcher(app_config=valid_app_config)
    release_searcher._use_release_type = True
    release_searcher._use_first_release_year = True
    release_searcher._use_record_label = True
    release_searcher._use_catalog_number = True
    lfm_rec = LFMRec(
        lfm_artist_str="Some+Artist",
        lfm_entity_str="Some+Bad+Album",
        recommendation_type=RecommendationType.ALBUM,
        rec_context=RecContext.SIMILAR_ARTIST,
    )
    actual_browse_params = release_searcher.create_red_browse_params(
        red_format=red_format,
        lfm_rec=lfm_rec,
        release_type=release_type,
        first_release_year=first_release_year,
        record_label=record_label,
        catalog_number=catalog_number,
    )
    assert (
        actual_browse_params == expected_browse_params
    ), f"Expected browse params to be '{expected_browse_params}', but got '{actual_browse_params}' instead."


def test_resolve_lfm_album_info(valid_app_config: AppConfig) -> None:
    with patch("requests.Session.get", side_effect=mock_lfm_session_get_side_effect) as mock_sesh_get:
        release_searcher = ReleaseSearcher(app_config=valid_app_config)
        test_lfm_rec = LFMRec(
            lfm_artist_str="Some+Artist",
            lfm_entity_str="Their+Album",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        )
        release_searcher._resolve_lfm_album_info(lfm_rec=test_lfm_rec)
        mock_sesh_get.assert_called_once_with(
            url="https://ws.audioscrobbler.com/2.0/?method=album.getinfo&api_key=5678alsonotarealapikey&artist=Some+Artist&album=Their+Album&format=json",
            headers={"Accept": "application/json"},
        )


@pytest.mark.parametrize(
    "test_lfm_rec, mock_lfm_json_fixture, mb_resolved_origin_release_fields, expected",
    [
        (
            LFMRec(
                lfm_artist_str="Dr.+Octagon",
                lfm_entity_str="No+Awareness",
                recommendation_type=RecommendationType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            "mock_full_lfm_track_info_json",
            None,
            LFMTrackInfo(
                artist="Dr. Octagon",
                track_name="No Awareness",
                release_name="Dr. Octagonecologyst",
                lfm_url="https://www.last.fm/music/Dr.+Octagon/_/No+Awareness",
                release_mbid="cddbf21f-9cd8-4665-a015-3cdc50cdcc72",
            ),
        ),
        (
            LFMRec(
                lfm_artist_str="The+Tuss",
                lfm_entity_str="rushup+i+bank+12+M",
                recommendation_type=RecommendationType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            "mock_no_album_lfm_track_info_json",
            {"origin_release_mbid": "3b08749b-b63e-46d3-b693-e0736faf046f", "origin_release_name": "Rushup Edge"},
            LFMTrackInfo(
                artist="The Tuss",
                track_name="rushup i bank 12 M",
                release_name="Rushup Edge",
                lfm_url="https://www.last.fm/music/The+Tuss/_/rushup+i+bank+12+M",
                release_mbid="3b08749b-b63e-46d3-b693-e0736faf046f",
            ),
        ),
        (
            LFMRec(
                lfm_artist_str="The+Tuss",
                lfm_entity_str="rushup+i+bank+12+M",
                recommendation_type=RecommendationType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            "mock_no_album_lfm_track_info_json",
            None,
            None,
        ),
        # (
        #     LFMRec(
        #         lfm_artist_str="The+Tuss",
        #         lfm_entity_str="rushup+i+bank+12+M",
        #         recommendation_type=RecommendationType.TRACK,
        #         rec_context=RecContext.IN_LIBRARY,
        #     ),
        #     "mock_lfm_track_info_raise_client_exception",
        #     None,
        #     None,
        # ),
    ],
)
def test_resolve_lfm_track_info(
    request: pytest.FixtureRequest,
    valid_app_config: AppConfig,
    test_lfm_rec: LFMRec,
    mock_lfm_json_fixture: str,
    mb_resolved_origin_release_fields: Optional[Dict[str, Optional[str]]],
    expected: Optional[LFMTrackInfo],
) -> None:
    mock_lfm_response = request.getfixturevalue(mock_lfm_json_fixture)["track"]
    with patch.object(LFMAPIClient, "request_api") as mock_lfm_request_api:
        mock_lfm_request_api.return_value = mock_lfm_response
        with patch.object(
            MusicBrainzAPIClient, "request_release_details_for_track"
        ) as mock_request_release_details_for_track:
            mock_request_release_details_for_track.return_value = mb_resolved_origin_release_fields
            release_searcher = ReleaseSearcher(app_config=valid_app_config)
            actual = release_searcher._resolve_lfm_track_info(lfm_rec=test_lfm_rec)
            mock_lfm_request_api.assert_called_once_with(
                method="track.getinfo", params=f"artist={test_lfm_rec.artist_str}&track={test_lfm_rec.entity_str}"
            )
            if "album" in mock_lfm_response:
                mock_request_release_details_for_track.assert_not_called()
            else:
                mock_request_release_details_for_track.assert_called_once()
            assert actual == expected, f"Expected {expected}, but got {actual}"


@pytest.mark.parametrize("lfm_api_response", [None, {"no-artist-key": "should-error"}])
def test_resolve_lfm_track_info_bad_json(
    valid_app_config: AppConfig,
    lfm_api_response: Optional[Dict[str, Any]],
) -> None:
    rec = LFMRec("Fake+Artist", "Fake+Song", RecommendationType.TRACK, RecContext.IN_LIBRARY)
    with patch.object(LFMAPIClient, "request_api") as mock_lfm_request_api:
        mock_lfm_request_api.return_value = lfm_api_response
        with patch.object(MusicBrainzAPIClient, "request_release_details_for_track") as mock_mb_request_method:
            mock_mb_request_method.return_value = {
                "origin_release_mbid": "69430-08749b-b",
                "origin_release_name": "Some Release",
            }
            release_searcher = ReleaseSearcher(app_config=valid_app_config)
            actual = release_searcher._resolve_lfm_track_info(lfm_rec=rec)
            assert actual is not None
            mock_mb_request_method.assert_called_once_with(
                human_readable_track_name=rec.get_human_readable_track_str(),
                artist_mbid=None,
                human_readable_artist_name=rec.get_human_readable_artist_str(),
            )


# @pytest.mark.parametrize(
#     "lfm_rec, lfm_json_fixture, expected", [
#         (
#             LFMRec("The+Tuss", "rushup+i+bank+12+M", RecommendationType.TRACK, RecContext.IN_LIBRARY),
#             "mock_lfm_track_info_raise_client_exception",
#             None,
#         ),
#         (
#             LFMRec("The+Tuss", "rushup+i+bank+12+M", RecommendationType.TRACK, RecContext.IN_LIBRARY),
#             "mock_lfm_track_info_raise_key_error_during_track_resolution",
#             None,
#         ),
#     ]
# )
# def test_resolve_lfm_track_info_client_exception(
#     request: pytest.FixtureRequest,
#     valid_app_config: AppConfig,
#     lfm_rec: LFMRec,
#     lfm_json_fixture: str,
#     expected: Optional[LFMTrackInfo],
# ) -> None:
#     mock_lfm_response = request.getfixturevalue(lfm_json_fixture)["track"]
#     with patch.object(LFMAPIClient, "request_api") as mock_lfm_request_api:
#         mock_lfm_request_api.return_value = mock_lfm_response
#         with patch.object(
#             MusicBrainzAPIClient, "request_release_details_for_track"
#         ) as mock_request_release_details_for_track:
#             mock_request_release_details_for_track.return_value = None
#             release_searcher = ReleaseSearcher(app_config=valid_app_config)
#             actual = release_searcher._resolve_lfm_track_info(lfm_rec=lfm_rec)
#             assert actual == expected, f"Expected {expected}, but got {actual}"


def test_resolve_mb_release(valid_app_config: AppConfig) -> None:
    with patch("requests.Session.get", side_effect=mock_mb_session_get_side_effect) as mock_sesh_get:
        release_searcher = ReleaseSearcher(app_config=valid_app_config)
        release_searcher._resolve_mb_release(mbid="some-fake-mbid")
        mock_sesh_get.assert_called_once_with(
            url="https://musicbrainz.org/ws/2/release/some-fake-mbid?inc=artist-credits+media+labels+release-groups",
            headers={"Accept": "application/json"},
        )


@pytest.mark.parametrize(
    "use_release_type, use_first_release_year, use_record_label, use_catalog_number, expected",
    [
        (False, False, False, False, False),
        (False, False, False, True, True),
        (False, False, True, False, True),
        (False, True, False, False, True),
        (True, False, False, False, True),
        (True, False, False, True, True),
        (True, False, True, False, True),
        (True, True, False, False, True),
        (True, True, False, True, True),
        (True, True, True, False, True),
        (True, True, True, True, True),
    ],
)
def test_require_mbid_resolution(
    use_release_type: bool,
    use_first_release_year: bool,
    use_record_label: bool,
    use_catalog_number: bool,
    expected: bool,
) -> None:
    actual = require_mbid_resolution(
        use_release_type=use_release_type,
        use_first_release_year=use_first_release_year,
        use_record_label=use_record_label,
        use_catalog_number=use_catalog_number,
    )
    assert actual == expected, f"Expected {expected}, but got {actual}"


def test_gather_red_user_details(valid_app_config: AppConfig) -> None:
    with patch("requests.Session.get", side_effect=mock_red_session_get_side_effect) as mock_sesh_get:
        with patch("plastered.utils.http_utils.precise_delay") as mock_precise_delay:
            mock_precise_delay.return_value = None
            release_searcher = ReleaseSearcher(app_config=valid_app_config)
            assert (
                release_searcher._red_user_details is None
            ), f"Expected ReleaseSearcher's initial value for _red_user_details attribute to be None, but got {type(release_searcher._red_user_details)}"
            release_searcher._gather_red_user_details()
            assert (
                release_searcher._red_user_details is not None
            ), f"Expected to not be None, but got {type(release_searcher._red_user_details)}"
            expected_red_user_id = release_searcher._red_user_id
            red_user_details_user_id = release_searcher._red_user_details.get_user_id()
            assert (
                red_user_details_user_id == expected_red_user_id
            ), f"Unexpected mismatch between release_searcher's _red_user_id attribute and the user_details' user_id attribute ({expected_red_user_id} vs. {red_user_details_user_id})"
            expected_snatch_count = 5216
            actual_snatch_count = release_searcher._red_user_details.get_snatched_count()
            assert (
                actual_snatch_count == expected_snatch_count
            ), f"Expected red_user_details' snatched_count value to be {expected_snatch_count}, but got {actual_snatch_count}"


@pytest.mark.parametrize(
    "exception_class_name, expected_snatch_failure_value",
    [
        (RedClientSnatchException.__name__, SnatchFailureReason.RED_API_REQUEST_ERROR.value),
        (OSError.__name__, SnatchFailureReason.FILE_ERROR.value),
        (Exception.__name__, SnatchFailureReason.OTHER.value),
    ],
)
def test_add_failed_snatch_row(
    valid_app_config: AppConfig,
    mock_best_te: TorrentEntry,
    exception_class_name: str,
    expected_snatch_failure_value: str,
) -> None:
    release_searcher = ReleaseSearcher(app_config=valid_app_config)
    release_searcher._add_failed_snatch_row(mock_best_te, exception_class_name=exception_class_name)
    expected = [[mock_best_te.get_permalink_url(), mock_best_te.get_matched_mbid(), expected_snatch_failure_value]]
    actual = release_searcher._failed_snatches_summary_rows
    assert expected == actual, f"expected {expected}, but got {actual}"


@pytest.mark.parametrize("mock_fl_token_used, expected_fl_col_val", [(False, "no"), (True, "yes")])
def test_add_snatch_row(
    tmp_path: pytest.FixtureRequest,
    valid_app_config: AppConfig,
    mock_best_te: TorrentEntry,
    mock_fl_token_used: bool,
    expected_fl_col_val: str,
) -> None:
    with patch.object(RedAPIClient, "tid_snatched_with_fl_token") as mock_red_client_fl_used_check:
        mock_red_client_fl_used_check.return_value = mock_fl_token_used
        mock_best_te.set_lfm_rec_fields(
            rec_type=RecommendationType.ALBUM.value,
            rec_context=RecContext.SIMILAR_ARTIST.value,
            artist_name="Fake Artist",
            release_name="Fake Release",
            track_rec_name=None,
        )
        mock_snatch_path = os.path.join(tmp_path, f"{mock_best_te.torrent_id}.torrent")
        release_searcher = ReleaseSearcher(app_config=valid_app_config)
        release_searcher._add_snatch_row(te=mock_best_te, snatch_path=mock_snatch_path)
        assert len(release_searcher._snatch_summary_rows) == 1
        mock_red_client_fl_used_check.assert_called_once_with(tid=mock_best_te.torrent_id)
        assert release_searcher._snatch_summary_rows[0] == [
            mock_best_te.get_lfm_rec_type(),
            mock_best_te.get_lfm_rec_context(),
            mock_best_te.get_artist_name(),
            mock_best_te.get_release_name(),
            "N/A",
            str(mock_best_te.torrent_id),
            mock_best_te.media,
            expected_fl_col_val,
            mock_snatch_path,
        ]


@pytest.mark.parametrize(
    "mock_response_fixture_names, mock_preference_ordering, expected_torrent_entry",
    [
        (  # Test case 1: empty browse results for first/only preference
            ["mock_red_browse_empty_response"],
            [RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.SACD)],
            None,
        ),
        (  # Test case 2: non-empty browse results for first preference
            ["mock_red_browse_non_empty_response"],
            [RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB)],
            TorrentEntry(
                torrent_id=69420,
                media="WEB",
                format="FLAC",
                encoding="24bit Lossless",
                size=69420,
                scene=False,
                trumpable=False,
                has_snatched=False,
                has_log=False,
                log_score=0,
                has_cue=False,
                can_use_token=False,
                reported=None,
                lossy_web=None,
                lossy_master=None,
            ),
        ),
        (  # Test case 3: empty browse results for first pref, and non-empty browse results for 2nd preference
            ["mock_red_browse_empty_response", "mock_red_browse_non_empty_response"],
            [
                RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.SACD),
                RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
            ],
            TorrentEntry(
                torrent_id=69420,
                media="WEB",
                format="FLAC",
                encoding="24bit Lossless",
                size=69420,
                scene=False,
                trumpable=False,
                has_snatched=False,
                has_log=False,
                log_score=0,
                has_cue=False,
                can_use_token=False,
                reported=None,
                lossy_web=None,
                lossy_master=None,
            ),
        ),
    ],
)  # TODO: Add test case for size over max_size filtering
def test_search_red_release_by_preferences(
    request: pytest.FixtureRequest,
    valid_app_config: AppConfig,
    mock_response_fixture_names: List[str],
    mock_preference_ordering: List[RedFormat],
    expected_torrent_entry: Optional[TorrentEntry],
) -> None:
    release_searcher = ReleaseSearcher(app_config=valid_app_config)
    release_searcher._red_format_preferences = mock_preference_ordering
    release_searcher._red_client.request_api = Mock(
        name="request_api",
        side_effect=[request.getfixturevalue(fixture_name)["response"] for fixture_name in mock_response_fixture_names],
    )
    actual_torrent_entry = release_searcher._search_red_release_by_preferences(
        lfm_rec=LFMRec(
            lfm_artist_str="Fake+Artist",
            lfm_entity_str="Fake+Release",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
        release_type=RedReleaseType.ALBUM,
        first_release_year=1899,
    )
    assert actual_torrent_entry == expected_torrent_entry


@pytest.mark.parametrize(
    "mock_response_fixture_names, mock_preference_ordering, expected_torrent_entry",
    [
        (  # Test case 3: empty browse results for first pref, and non-empty browse results for 2nd preference
            ["mock_red_browse_empty_response", "mock_red_browse_non_empty_response"],
            [
                RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.SACD),
                RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
            ],
            None,
        ),
    ],
)  # TODO: Add test case for size over max_size filtering
def test_search_red_release_by_preferences_above_max_size_found(
    request: pytest.FixtureRequest,
    valid_app_config: AppConfig,
    mock_response_fixture_names: List[str],
    mock_preference_ordering: List[RedFormat],
    expected_torrent_entry: Optional[TorrentEntry],
) -> None:
    test_lfm_rec = LFMRec(
        lfm_artist_str="Fake+Artist",
        lfm_entity_str="Fake+Release",
        recommendation_type=RecommendationType.ALBUM,
        rec_context=RecContext.IN_LIBRARY,
    )
    with patch.object(ReleaseSearcher, "_add_skipped_snatch_row") as mock_add_skipped_snatch_row:
        mock_add_skipped_snatch_row.return_value = None
        release_searcher = ReleaseSearcher(app_config=valid_app_config)
        release_searcher._max_size_gb = 0.00001
        release_searcher._red_format_preferences = mock_preference_ordering
        release_searcher._red_client.request_api = Mock(
            name="request_api",
            side_effect=[
                request.getfixturevalue(fixture_name)["response"] for fixture_name in mock_response_fixture_names
            ],
        )
        actual_torrent_entry = release_searcher._search_red_release_by_preferences(
            lfm_rec=test_lfm_rec,
            release_type=RedReleaseType.ALBUM,
            first_release_year=1899,
        )
        assert actual_torrent_entry == expected_torrent_entry
        mock_add_skipped_snatch_row.assert_called_once_with(rec=test_lfm_rec, reason=SkippedReason.ABOVE_MAX_SIZE)


def test_search_red_release_by_preferences_browse_exception_raised(
    valid_app_config: AppConfig,
) -> None:
    def _raise_excp(*args, **kwargs) -> None:
        raise Exception(f"Fake exception")

    test_lfm_rec = LFMRec(
        lfm_artist_str="Fake+Artist",
        lfm_entity_str="Fake+Release",
        recommendation_type=RecommendationType.ALBUM,
        rec_context=RecContext.IN_LIBRARY,
    )
    with patch("plastered.release_search.release_searcher._LOGGER") as mock_logger:
        mock_logger.error.return_value = None
        release_searcher = ReleaseSearcher(app_config=valid_app_config)
        release_searcher._red_format_preferences = [
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.SACD),
        ]
        release_searcher._red_client.request_api = Mock(name="request_api", side_effect=_raise_excp)

        actual = release_searcher._search_red_release_by_preferences(
            lfm_rec=test_lfm_rec,
            release_type=RedReleaseType.ALBUM,
            first_release_year=1899,
        )
        assert actual is None, f"Expected None, but got {actual}"
        mock_logger.error.assert_called_once()


@pytest.mark.parametrize(
    "lfm_rec, mock_tids_to_snatch, mock_red_user_has_snatched_tid_result, expected, expected_add_skip_row_call_kwargs",
    [
        (  # case 1: current best_te's TID already exists in the current to_snatch list
            LFMRec("The+Tuss", "rushup+i+bank+12+M", RecommendationType.TRACK, RecContext.IN_LIBRARY),
            set([69420]),
            False,
            False,
            {
                "rec": LFMRec("The+Tuss", "rushup+i+bank+12+M", RecommendationType.TRACK, RecContext.IN_LIBRARY),
                "reason": SkippedReason.DUPE_OF_ANOTHER_REC,
            },
        ),
        (  # case 2: current best_te's TID already marked as snatched or seeding by red user details
            LFMRec("The+Tuss", "rushup+i+bank+12+M", RecommendationType.TRACK, RecContext.IN_LIBRARY),
            set([100]),
            True,
            False,
            {
                "rec": LFMRec("The+Tuss", "rushup+i+bank+12+M", RecommendationType.TRACK, RecContext.IN_LIBRARY),
                "reason": SkippedReason.ALREADY_SNATCHED,
                "matched_tid": 69420,
            },
        ),
    ],
)
def test_post_search_filter(
    valid_app_config: AppConfig,
    mock_best_te: TorrentEntry,
    mock_red_user_details: RedUserDetails,
    lfm_rec: LFMRec,
    mock_tids_to_snatch: Set[int],
    mock_red_user_has_snatched_tid_result: bool,
    expected: bool,
    expected_add_skip_row_call_kwargs: Optional[Dict[str, Any]],
) -> None:
    with patch("requests.Session.get", side_effect=mock_lfm_session_get_side_effect) as mock_sesh_get:
        with patch.object(RedUserDetails, "has_snatched_tid") as mock_rud_has_snatched_tid:
            with patch.object(ReleaseSearcher, "_add_skipped_snatch_row") as mock_add_skipped_snatch_row:
                mock_add_skipped_snatch_row.return_value = None
                mock_rud_has_snatched_tid.return_value = mock_red_user_has_snatched_tid_result
                release_searcher = ReleaseSearcher(app_config=valid_app_config)
                release_searcher._red_user_details = mock_red_user_details
                release_searcher._tids_to_snatch = mock_tids_to_snatch
                actual = release_searcher._post_search_filter(lfm_rec=lfm_rec, best_te=mock_best_te)
                assert actual == expected, f"Expected {expected} but got {actual}"
                if expected_add_skip_row_call_kwargs:
                    mock_add_skipped_snatch_row.assert_called_once_with(**expected_add_skip_row_call_kwargs)


# TODO (later): clean up this nightmare of a test function
@pytest.mark.parametrize(
    "use_release_type, use_first_release_year, use_record_label, use_catalog_number, found_te, mbid_result",
    [
        (False, False, False, False, False, None),
        (False, False, False, False, True, None),
        (True, False, False, False, False, None),
        (False, False, False, True, True, "1234"),
        (False, False, True, False, True, "1234"),
        (False, True, False, False, True, "1234"),
        (True, False, False, False, True, "1234"),
        (True, True, True, True, False, "1234"),
        (True, True, True, True, True, "1234"),
    ],
)
def test_search_for_album_rec(
    use_release_type: bool,
    use_first_release_year: bool,
    use_record_label: bool,
    use_catalog_number: bool,
    found_te: bool,
    mbid_result: str,
    mock_lfmai: LFMAlbumInfo,
    mock_mbr: MBRelease,
    mock_best_te: TorrentEntry,
    valid_app_config: AppConfig,
    mock_red_user_details: RedUserDetails,
) -> None:
    expected_search_kwargs = (
        {
            "release_type": RedReleaseType.ALBUM,
            "first_release_year": 2016,
            "record_label": "Get On Down",
            "catalog_number": "58010",
        }
        if (use_release_type or use_first_release_year or use_record_label or use_catalog_number)
        else {}
    )
    mock_artist, mock_release = "Foo", "Bar"
    expected_te_result = (
        TorrentEntry(
            torrent_id=69420,
            media="WEB",
            format="FLAC",
            encoding="24bit Lossless",
            size=69420,
            scene=False,
            trumpable=False,
            has_snatched=False,
            has_log=False,
            log_score=0,
            has_cue=False,
            can_use_token=False,
        )
        if found_te
        else None
    )
    if found_te and mbid_result:
        expected_te_result.set_matched_mbid(matched_mbid=mbid_result)
    if found_te:
        expected_te_result.set_lfm_rec_fields(
            rec_type="album", rec_context="similar-artist", artist_name=mock_artist, release_name=mock_release
        )
    override_app_conf_options = {
        "use_release_type": use_release_type,
        "use_first_release_year": use_first_release_year,
        "use_record_label": use_record_label,
        "use_catalog_number": use_catalog_number,
    }
    mocked_cli_options = {**valid_app_config._cli_options, **override_app_conf_options}

    def _get_opt_side_effect(*args, **kwargs) -> Any:
        return mocked_cli_options[args[0]]

    with patch.object(AppConfig, "get_cli_option") as mock_app_conf_get_cli_option:
        mock_app_conf_get_cli_option.side_effect = _get_opt_side_effect
        release_searcher = ReleaseSearcher(app_config=valid_app_config)
        release_searcher._search_red_release_by_preferences = Mock(name="_search_red_release_by_preferences")
        release_searcher._search_red_release_by_preferences.return_value = mock_best_te if found_te else None
        release_searcher._resolve_lfm_album_info = Mock(name="_resolve_lfm_album_info")
        release_searcher._resolve_lfm_album_info.return_value = mock_lfmai
        release_searcher._resolve_mb_release = Mock(name="_resolve_mb_release")
        release_searcher._resolve_mb_release.return_value = mock_mbr
        release_searcher._red_user_details = mock_red_user_details
        test_lfm_rec = LFMRec(
            lfm_artist_str=mock_artist,
            lfm_entity_str=mock_release,
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        )
        actual = release_searcher.search_for_release_rec(lfm_rec=test_lfm_rec)
        if release_searcher._require_mbid_resolution:
            release_searcher._resolve_lfm_album_info.assert_called_once()
            release_searcher._resolve_mb_release.assert_called_once_with(mbid=mock_lfmai.get_release_mbid())
        else:
            release_searcher._resolve_lfm_album_info.assert_not_called()
            release_searcher._resolve_mb_release.assert_not_called()
        release_searcher._search_red_release_by_preferences.assert_called_once_with(
            lfm_rec=test_lfm_rec, search_kwargs=expected_search_kwargs
        )
        assert actual == expected_te_result, f"Expected result: {expected_te_result}, but got {actual}"


@pytest.mark.parametrize(
    "lfm_artist_str, lfm_album_str, expected_search_artist_str, expected_search_release_str",
    [
        (
            "Some+Artist",
            "Some+Album",
            "Some Artist",
            "Some Album",
        ),
        (
            "Some+Artist",
            "This+Nation%27s+Saving+Grace",
            "Some Artist",
            "This Nation's Saving Grace",
        ),
    ],
)
def test_search_for_album_rec_skip_prior_snatch(
    lfm_artist_str: str,
    lfm_album_str: str,
    expected_search_artist_str: str,
    expected_search_release_str: str,
    valid_app_config: AppConfig,
    mock_red_user_details: RedUserDetails,
) -> None:
    with patch.object(LFMAlbumInfo, "construct_from_api_response") as mock_lfmai_class_method:
        with patch.object(MBRelease, "construct_from_api") as mock_mbr_class_method:
            with patch.object(ReleaseSearcher, "_search_red_release_by_preferences") as mock_rfp_search:
                release_searcher = ReleaseSearcher(app_config=valid_app_config)
                release_searcher._red_user_details = mock_red_user_details
                with patch.object(RedUserDetails, "has_snatched_release") as mock_rud_has_snatched_release:
                    mock_rud_has_snatched_release.return_value = True
                    actual_search_result = release_searcher.search_for_release_rec(
                        lfm_rec=LFMRec(
                            lfm_artist_str=lfm_artist_str,
                            lfm_entity_str=lfm_album_str,
                            recommendation_type=RecommendationType.ALBUM,
                            rec_context=RecContext.SIMILAR_ARTIST,
                        )
                    )
                    mock_rud_has_snatched_release.assert_called_once_with(
                        artist=expected_search_artist_str, release=expected_search_release_str
                    )
                    assert (
                        actual_search_result is None
                    ), f"Expected pre-snatched release to cause search_for_album_rec to return None, but got {actual_search_result}"


# ("https://redacted.sh/torrents.php?torrentid=123", None)


@pytest.mark.parametrize(
    "rec_context, allow_library_items, expect_found",
    [
        (RecContext.SIMILAR_ARTIST, False, True),
        (RecContext.SIMILAR_ARTIST, True, True),
        (RecContext.IN_LIBRARY, False, False),
        (RecContext.IN_LIBRARY, True, True),
    ],
)
def test_search_for_album_rec_allow_library_items(
    valid_app_config: AppConfig,
    no_snatch_user_details: RedUserDetails,
    rec_context: RecContext,
    allow_library_items: bool,
    expect_found: bool,
) -> None:
    lfm_rec = LFMRec(
        lfm_artist_str="Some+Artist",
        lfm_entity_str="Some+Album",
        recommendation_type=RecommendationType.ALBUM,
        rec_context=rec_context,
    )
    with patch.object(ReleaseSearcher, "_search_red_release_by_preferences") as mock_rfp_search:
        release_searcher = ReleaseSearcher(app_config=valid_app_config)
        release_searcher._red_user_details = no_snatch_user_details
        release_searcher._skip_prior_snatches = False
        release_searcher._allow_library_items = allow_library_items
        release_searcher._require_mbid_resolution = False
        res_te = TorrentEntry(
            torrent_id=123,
            media="CD",
            format="FLAC",
            encoding="Lossless",
            size=12345,
            scene=False,
            trumpable=False,
            has_snatched=False,
            has_log=True,
            log_score=100,
            has_cue=True,
            can_use_token=False,
        )
        mock_rfp_search.return_value = res_te
        expected = res_te if expect_found else None
        actual_result = release_searcher.search_for_release_rec(lfm_rec=lfm_rec)
        assert (
            actual_result == expected
        ), f"Expected search result to be {expected} for allow_library_items set to {allow_library_items} and rec_context set to {rec_context}, but got {actual_result}"


@pytest.mark.parametrize(
    "lfm_recs, mocked_search_results, expected_to_snatch_length",
    [
        ([], [], 0),
        (
            [
                LFMRec(
                    lfm_artist_str="Some+Artist",
                    lfm_entity_str="Their+Album",
                    recommendation_type=RecommendationType.ALBUM,
                    rec_context=RecContext.SIMILAR_ARTIST,
                )
            ],
            [None],
            0,
        ),
        (
            [
                LFMRec(
                    lfm_artist_str="Some+Artist",
                    lfm_entity_str="Their+Album",
                    recommendation_type=RecommendationType.ALBUM,
                    rec_context=RecContext.SIMILAR_ARTIST,
                )
            ],
            [
                TorrentEntry(
                    torrent_id=69420,
                    media="CD",
                    format="FLAC",
                    encoding="Lossless",
                    size=12345,
                    scene=False,
                    trumpable=False,
                    has_snatched=False,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    can_use_token=False,
                ),
            ],
            1,
        ),
        (
            [
                LFMRec(
                    lfm_artist_str="Some+Artist",
                    lfm_entity_str="Their+Album",
                    recommendation_type=RecommendationType.ALBUM,
                    rec_context=RecContext.SIMILAR_ARTIST,
                )
            ],
            [
                TorrentEntry(
                    torrent_id=69420,
                    media="CD",
                    format="FLAC",
                    encoding="Lossless",
                    size=12345,
                    scene=False,
                    trumpable=False,
                    has_snatched=False,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    can_use_token=False,
                ),
            ],
            1,
        ),
        (
            [
                LFMRec(
                    lfm_artist_str="Some+Artist",
                    lfm_entity_str="Their+Album",
                    recommendation_type=RecommendationType.ALBUM,
                    rec_context=RecContext.SIMILAR_ARTIST,
                ),
                LFMRec(
                    lfm_artist_str="Some+Other+Artist",
                    lfm_entity_str="Some+Other+Album",
                    recommendation_type=RecommendationType.ALBUM,
                    rec_context=RecContext.IN_LIBRARY,
                ),
                LFMRec(
                    lfm_artist_str="Some+Bad+Artist",
                    lfm_entity_str="Bad+Album",
                    recommendation_type=RecommendationType.ALBUM,
                    rec_context=RecContext.IN_LIBRARY,
                ),
            ],
            [
                TorrentEntry(
                    torrent_id=69420,
                    media="CD",
                    format="FLAC",
                    encoding="Lossless",
                    size=12345,
                    scene=False,
                    trumpable=False,
                    has_snatched=False,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    can_use_token=False,
                ),
                None,
                TorrentEntry(
                    torrent_id=666,
                    media="CD",
                    format="FLAC",
                    encoding="Lossless",
                    size=12345,
                    scene=False,
                    trumpable=False,
                    has_snatched=False,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    can_use_token=False,
                ),
            ],
            2,
        ),
    ],
)
def test_search_for_album_recs(
    lfm_recs: List[LFMRec],
    mocked_search_results: List[Optional[Tuple[str, Optional[str]]]],
    expected_to_snatch_length: int,
    valid_app_config: AppConfig,
    mock_red_user_details: RedUserDetails,
) -> None:
    search_res_q = deque(mocked_search_results)
    expected_te_to_snatch_entries = [te for te in mocked_search_results if te is not None]

    def mock_search_side_effect(*args, **kwargs) -> Optional[Tuple[str, Optional[str]]]:
        return search_res_q.popleft()

    with patch.object(ReleaseSearcher, "search_for_release_rec") as mock_search_for_release_rec:
        mock_search_for_release_rec.side_effect = mock_search_side_effect
        release_searcher = ReleaseSearcher(app_config=valid_app_config)
        release_searcher._red_user_details = release_searcher._red_user_details = mock_red_user_details
        release_searcher._search_for_release_recs(lfm_recs=lfm_recs)
        actual_to_snatch_len = len(release_searcher._torrent_entries_to_snatch)
        assert (
            actual_to_snatch_len == expected_to_snatch_length
        ), f"Expected {expected_to_snatch_length} entries in _torrent_entries_to_snatch, but got {actual_to_snatch_len} instead."
        for i, actual_te in enumerate(release_searcher._torrent_entries_to_snatch):
            expected_te = expected_te_to_snatch_entries[i]
            assert actual_te == expected_te, f"Expected TorrentEntry: {expected_te}, but got {actual_te}"


@pytest.mark.parametrize(
    "lfm_recs, mocked_search_results, expected_to_snatch_length",
    [
        ([], [], 0),
        (
            [
                LFMRec(
                    lfm_artist_str="Some+Artist",
                    lfm_entity_str="Their+Song",
                    recommendation_type=RecommendationType.TRACK,
                    rec_context=RecContext.SIMILAR_ARTIST,
                )
            ],
            [None],
            0,
        ),
        (
            [
                LFMRec(
                    lfm_artist_str="Some+Artist",
                    lfm_entity_str="Their+Track",
                    recommendation_type=RecommendationType.TRACK,
                    rec_context=RecContext.SIMILAR_ARTIST,
                )
            ],
            [
                TorrentEntry(
                    torrent_id=69420,
                    media="CD",
                    format="FLAC",
                    encoding="Lossless",
                    size=12345,
                    scene=False,
                    trumpable=False,
                    has_snatched=False,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    can_use_token=False,
                ),
            ],
            1,
        ),
        (
            [
                LFMRec(
                    lfm_artist_str="Some+Artist",
                    lfm_entity_str="Their+Song",
                    recommendation_type=RecommendationType.TRACK,
                    rec_context=RecContext.SIMILAR_ARTIST,
                )
            ],
            [
                TorrentEntry(
                    torrent_id=69420,
                    media="CD",
                    format="FLAC",
                    encoding="Lossless",
                    size=12345,
                    scene=False,
                    trumpable=False,
                    has_snatched=False,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    can_use_token=False,
                ),
            ],
            1,
        ),
        (
            [
                LFMRec(
                    lfm_artist_str="Some+Artist",
                    lfm_entity_str="Their+Song",
                    recommendation_type=RecommendationType.TRACK,
                    rec_context=RecContext.SIMILAR_ARTIST,
                ),
                LFMRec(
                    lfm_artist_str="Some+Other+Artist",
                    lfm_entity_str="Some+Other+Track",
                    recommendation_type=RecommendationType.TRACK,
                    rec_context=RecContext.IN_LIBRARY,
                ),
                LFMRec(
                    lfm_artist_str="Some+Bad+Artist",
                    lfm_entity_str="Bad+Track",
                    recommendation_type=RecommendationType.TRACK,
                    rec_context=RecContext.IN_LIBRARY,
                ),
            ],
            [
                TorrentEntry(
                    torrent_id=69420,
                    media="CD",
                    format="FLAC",
                    encoding="Lossless",
                    size=12345,
                    scene=False,
                    trumpable=False,
                    has_snatched=False,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    can_use_token=False,
                ),
                None,
                TorrentEntry(
                    torrent_id=666,
                    media="CD",
                    format="FLAC",
                    encoding="Lossless",
                    size=12345,
                    scene=False,
                    trumpable=False,
                    has_snatched=False,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    can_use_token=False,
                ),
            ],
            2,
        ),
    ],
)
def test_search_for_release_recs_tracks(
    lfm_recs: List[LFMRec],
    mocked_search_results: List[Optional[Tuple[str, Optional[str]]]],
    expected_to_snatch_length: int,
    valid_app_config: AppConfig,
    mock_red_user_details: RedUserDetails,
) -> None:
    pass  # TODO
    search_res_q = deque(mocked_search_results)
    expected_te_to_snatch_entries = [te for te in mocked_search_results if te is not None]

    def mock_search_side_effect(*args, **kwargs) -> Optional[Tuple[str, Optional[str]]]:
        return search_res_q.popleft()

    with patch.object(ReleaseSearcher, "search_for_release_rec") as mock_search_for_release_rec:
        mock_search_for_release_rec.side_effect = mock_search_side_effect
        release_searcher = ReleaseSearcher(app_config=valid_app_config)
        release_searcher._red_user_details = release_searcher._red_user_details = mock_red_user_details
        release_searcher._search_for_release_recs(lfm_recs=lfm_recs)
        actual_to_snatch_len = len(release_searcher._torrent_entries_to_snatch)
        assert (
            actual_to_snatch_len == expected_to_snatch_length
        ), f"Expected {expected_to_snatch_length} entries in _torrent_entries_to_snatch, but got {actual_to_snatch_len} instead."
        for i, actual_te in enumerate(release_searcher._torrent_entries_to_snatch):
            expected_te = expected_te_to_snatch_entries[i]
            assert actual_te == expected_te, f"Expected TorrentEntry: {expected_te}, but got {actual_te}"


@pytest.mark.parametrize(
    "mock_resolve_lfm_result",
    [
        (None),
        (LFMTrackInfo("Some Artist", "Track Title", "Source Album", "https://fake-url", "69-420")),
    ],
)
def test_search_for_track_recs(valid_app_config: AppConfig, mock_resolve_lfm_result: Optional[LFMTrackInfo]) -> None:
    test_lfm_rec = LFMRec("Some+Artist", "Track+Title", RecommendationType.TRACK, RecContext.SIMILAR_ARTIST)
    with patch.object(ReleaseSearcher, "_search_for_release_recs") as mock_search_for_release_recs:
        with patch.object(ReleaseSearcher, "_resolve_lfm_track_info") as mock_resolve_lfm_track_info:
            mock_resolve_lfm_track_info.return_value = mock_resolve_lfm_result
            mock_search_for_release_recs.return_value = None
            release_searcher = ReleaseSearcher(app_config=valid_app_config)
            release_searcher._search_for_track_recs(track_recs=[test_lfm_rec])
            mock_resolve_lfm_track_info.assert_called_once_with(lfm_rec=test_lfm_rec)
            if not mock_resolve_lfm_result:
                mock_search_for_release_recs.assert_called_once_with(lfm_recs=[])
            else:
                assert test_lfm_rec.get_human_readable_release_str() == mock_resolve_lfm_result.get_release_name()
                assert test_lfm_rec.track_origin_release_mbid == mock_resolve_lfm_result.get_release_mbid()
                mock_search_for_release_recs.assert_called_once_with(lfm_recs=[test_lfm_rec])


@pytest.mark.parametrize(
    "rec_type_to_recs_list, expected_search_for_release_recs_calls",
    [
        ({}, 0),
        (
            {
                RecommendationType.ALBUM: [
                    LFMRec("Some+Artist", "Some+Album", RecommendationType.ALBUM, RecContext.SIMILAR_ARTIST),
                ]
            },
            1,
        ),
        (
            {
                RecommendationType.TRACK: [
                    LFMRec("Some+Artist", "Some+Track", RecommendationType.TRACK, RecContext.IN_LIBRARY),
                ]
            },
            1,
        ),
        (
            {
                RecommendationType.ALBUM: [
                    LFMRec("Some+Artist", "Some+Album", RecommendationType.ALBUM, RecContext.SIMILAR_ARTIST),
                ],
                RecommendationType.TRACK: [
                    LFMRec("Some+Artist", "Some+Track", RecommendationType.TRACK, RecContext.IN_LIBRARY),
                ],
            },
            2,
        ),
    ],
)
def test_search_for_recs(
    valid_app_config: AppConfig,
    mock_lfm_track_info: LFMTrackInfo,
    rec_type_to_recs_list: Dict[RecommendationType, List[LFMRec]],
    expected_search_for_release_recs_calls: int,
) -> None:
    with patch.object(ReleaseSearcher, "_gather_red_user_details") as mock_gather_red_user_details:
        with patch.object(ReleaseSearcher, "_search_for_release_recs") as mock_search_for_release_recs:
            with patch.object(ReleaseSearcher, "_resolve_lfm_track_info") as mock_resolve_lfm_track_info:
                with patch.object(ReleaseSearcher, "_snatch_matches") as mock_snatch_matches:
                    mock_gather_red_user_details.return_value = None
                    mock_search_for_release_recs.return_value = None
                    mock_resolve_lfm_track_info.return_value = mock_lfm_track_info
                    mock_snatch_matches.return_value = None
                    release_searcher = ReleaseSearcher(app_config=valid_app_config)
                    release_searcher.search_for_recs(rec_type_to_recs_list=rec_type_to_recs_list)
                    mock_gather_red_user_details.assert_called_once()
                    actual_num_search_for_release_recs_calls = len(mock_search_for_release_recs.mock_calls)
                    assert (
                        actual_num_search_for_release_recs_calls == expected_search_for_release_recs_calls
                    ), f"Expected _search_for_release_recs to be called exactly {expected_search_for_release_recs_calls} times, but found: {actual_num_search_for_release_recs_calls}"
                    mock_snatch_matches.assert_called_once()


def test_search_for_album_recs_invalid_user_details(valid_app_config: AppConfig) -> None:
    with pytest.raises(ReleaseSearcherException, match="self._red_user_details has not yet been populated"):
        release_searcher = ReleaseSearcher(app_config=valid_app_config)
        release_searcher._search_for_release_recs(
            lfm_recs=[LFMRec("A", "B", RecommendationType.ALBUM, RecContext.IN_LIBRARY)],
        )


def test_search_for_release_recs_mixed_rec_types(valid_app_config: AppConfig) -> None:
    with pytest.raises(
        ReleaseSearcherException, match=f"Invalid lfm_recs list. All recs in list must have the same rec_type value"
    ):
        release_searcher = ReleaseSearcher(app_config=valid_app_config)
        release_searcher._search_for_release_recs(
            lfm_recs=[
                LFMRec("A", "B", RecommendationType.ALBUM, RecContext.IN_LIBRARY),
                LFMRec("C", "D", RecommendationType.TRACK, RecContext.IN_LIBRARY),
            ],
        )


@pytest.mark.parametrize(
    "mock_enable_snatches, mock_tes_to_snatch, expected_out_filenames, expected_request_params",
    [
        (False, [], [], []),
        (True, [], [], []),
        (
            False,
            [
                TorrentEntry(
                    torrent_id=69420,
                    media="CD",
                    format="FLAC",
                    encoding="Lossless",
                    size=12345,
                    scene=False,
                    trumpable=False,
                    has_snatched=False,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    can_use_token=False,
                ),
                TorrentEntry(
                    torrent_id=666,
                    media="CD",
                    format="FLAC",
                    encoding="Lossless",
                    size=12345,
                    scene=False,
                    trumpable=False,
                    has_snatched=False,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    can_use_token=False,
                ),
            ],
            [],
            [],
        ),
        (
            True,
            [
                TorrentEntry(
                    torrent_id=69420,
                    media="CD",
                    format="FLAC",
                    encoding="Lossless",
                    size=12345,
                    scene=False,
                    trumpable=False,
                    has_snatched=False,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    can_use_token=False,
                ),
                TorrentEntry(
                    torrent_id=666,
                    media="CD",
                    format="FLAC",
                    encoding="Lossless",
                    size=12345,
                    scene=False,
                    trumpable=False,
                    has_snatched=False,
                    has_log=True,
                    log_score=100,
                    has_cue=True,
                    can_use_token=False,
                ),
            ],
            ["69420.torrent", "666.torrent"],
            ["69420", "666"],
        ),
    ],
)
def test_snatch_matches(
    tmp_path: pytest.FixtureRequest,
    valid_app_config: AppConfig,
    mock_enable_snatches: bool,
    mock_tes_to_snatch: List[TorrentEntry],
    expected_out_filenames: List[str],
    expected_request_params: List[str],
) -> None:
    mocked_cli_options = {
        **valid_app_config._cli_options,
        **{"snatch_recs": mock_enable_snatches, "snatch_directory": tmp_path},
    }

    def _get_opt_side_effect(*args, **kwargs) -> Any:
        return mocked_cli_options[args[0]]

    with patch.object(AppConfig, "get_cli_option") as mock_app_conf_get_cli_option:
        mock_app_conf_get_cli_option.side_effect = _get_opt_side_effect
        with patch.object(RedAPIClient, "snatch") as mock_red_client_snatch:
            mock_red_client_snatch.return_value = bytes("fakedata", encoding="utf-8")
            expected_output_filepaths = [os.path.join(tmp_path, filename) for filename in expected_out_filenames]
            release_searcher = ReleaseSearcher(app_config=valid_app_config)
            release_searcher._torrent_entries_to_snatch = mock_tes_to_snatch
            release_searcher._snatch_matches()
            print(f"mock_red_client_snatch.mock_calls: {mock_red_client_snatch.mock_calls}")
            if not mock_enable_snatches:
                mock_red_client_snatch.assert_not_called()
                assert all([not tmp_filename.endswith(".torrent") for tmp_filename in os.listdir(tmp_path)])
            else:
                mock_red_client_snatch.assert_has_calls(
                    [
                        call(tid=expected_request_param, can_use_token_on_torrent=False)
                        for expected_request_param in expected_request_params
                    ]
                )
                assert all([os.path.exists(out_filepath) for out_filepath in expected_output_filepaths])


@pytest.mark.parametrize(
    "exception_type, mock_file_exists",
    [
        (RedClientSnatchException, False),
        (RedClientSnatchException, True),
        (OSError, False),
        (OSError, True),
    ],
)
def test_snatch_exception_handling(
    tmp_path: pytest.FixtureRequest,
    valid_app_config: AppConfig,
    mock_best_te: TorrentEntry,
    exception_type: Exception,
    mock_file_exists: bool,
) -> None:
    print(f"exception_type.__name__: {exception_type.__name__}")

    def _red_client_raise_exception_side_effect(*args, **kwargs) -> None:
        raise exception_type("Expected testing exception")

    with patch.object(AppConfig, "get_cli_option") as mock_app_conf_get_cli_option:
        mock_app_conf_get_cli_option.side_effect = lambda x: (
            tmp_path if x == "snatch_directory" else valid_app_config._cli_options[x]
        )
        with patch.object(RedAPIClient, "snatch") as mock_red_client_snatch:
            mock_red_client_snatch.side_effect = _red_client_raise_exception_side_effect
            expected_out_filepath = os.path.join(tmp_path, "69420.torrent")
            release_searcher = ReleaseSearcher(app_config=valid_app_config)
            release_searcher._torrent_entries_to_snatch = [mock_best_te]
            if mock_file_exists:
                with open(expected_out_filepath, "wb") as tf:
                    tf.write(bytes("fakedata", encoding="utf-8"))
            release_searcher._snatch_matches()
            assert not os.path.exists(expected_out_filepath)
            expected_failed_snatch_rows = [
                [
                    mock_best_te.get_permalink_url(),
                    mock_best_te.get_matched_mbid(),
                    exception_type.__name__,
                ],
            ]
            actual_failed_snatch_rows = release_searcher._failed_snatches_summary_rows
            assert (
                actual_failed_snatch_rows == expected_failed_snatch_rows
            ), f"expected {expected_failed_snatch_rows}, but got {actual_failed_snatch_rows}"


def test_generate_summary_stats(tmp_path: pytest.FixtureRequest, valid_app_config: AppConfig) -> None:
    with patch(
        "plastered.release_search.release_searcher.print_and_save_all_searcher_stats"
    ) as mock_print_and_save_all_searcher_stats:
        release_searcher = ReleaseSearcher(app_config=valid_app_config)
        mock_output_summary_filepath_prefix = os.path.join(tmp_path, "1969-12-31__10-10-59")
        release_searcher._output_summary_filepath_prefix = mock_output_summary_filepath_prefix
        mock_print_and_save_all_searcher_stats.return_value = None
        release_searcher.generate_summary_stats()
        mock_print_and_save_all_searcher_stats.assert_called_once_with(
            skipped_rows=[],
            failed_snatch_rows=[],
            snatch_summary_rows=[],
            output_filepath_prefix=mock_output_summary_filepath_prefix,
        )
