import os
from collections import deque
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import Mock, call, patch

import pytest

from lastfm_recs_scraper.config.config_parser import AppConfig
from lastfm_recs_scraper.release_search.release_searcher import (
    ReleaseSearcher,
    create_red_browse_params,
    lastfm_format_to_user_details_format,
    require_mbid_resolution,
)
from lastfm_recs_scraper.scraper.last_scraper import (
    LastFMRec,
    RecContext,
    RecommendationType,
)
from lastfm_recs_scraper.utils.exceptions import ReleaseSearcherException
from lastfm_recs_scraper.utils.http_utils import (
    LastFMAPIClient,
    MusicBrainzAPIClient,
    RedAPIClient,
)
from lastfm_recs_scraper.utils.lastfm_utils import LastFMAlbumInfo
from lastfm_recs_scraper.utils.musicbrainz_utils import MBRelease
from lastfm_recs_scraper.utils.red_utils import (
    EncodingEnum,
    FormatEnum,
    MediaEnum,
    RedFormat,
    RedReleaseType,
    RedUserDetails,
    TorrentEntry,
)
from tests.conftest import (
    mock_red_session_get_side_effect,
    mock_red_user_details,
    mock_red_user_stats_response,
    mock_red_user_torrents_response,
    valid_app_config,
)

_EXPECTED_TSV_OUTPUT_HEADER = "entity_type\trec_context\tlastfm_entity_url\tred_permalink\trelease_mbid\n"


@pytest.fixture(scope="session")
def mock_lfmai() -> LastFMAlbumInfo:
    return LastFMAlbumInfo(artist="Foo", release_mbid="1234", album_name="Bar", lastfm_url="https://blah.com")


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


@pytest.fixture(scope="session")
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
    red_format: RedFormat,
    release_type: Optional[RedReleaseType],
    first_release_year: Optional[int],
    record_label: Optional[str],
    catalog_number: Optional[str],
    expected_browse_params: str,
) -> None:
    fake_artist_name = "Some+Artist"
    fake_album_name = "Some+Bad+Album"
    actual_browse_params = create_red_browse_params(
        red_format=red_format,
        artist_name=fake_artist_name,
        album_name=fake_album_name,
        release_type=release_type,
        first_release_year=first_release_year,
        record_label=record_label,
        catalog_number=catalog_number,
    )
    assert (
        actual_browse_params == expected_browse_params
    ), f"Expected browse params to be '{expected_browse_params}', but got '{actual_browse_params}' instead."


def test_release_searcher_init(valid_app_config: AppConfig) -> None:
    release_searcher = ReleaseSearcher(app_config=valid_app_config)
    pass  # TODO: implement


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


@pytest.mark.parametrize(
    "user_torrent_str, expected",
    [
        ("", ""),
        ("singleword", "singleword"),
        ("lowercase", "lowercase"),
        ("aphex+twin", "aphex twin"),
        ("aphex twin", "aphex twin"),
        ("double+nickels+on+the+dime", "double nickels on the dime"),
        ("dr.+octagonecologyst", "dr. octagonecologyst"),
        ("much+against+everyone%27s+advice", "much against everyone's advice"),
        ("signals,+calls+and+marches", "signals, calls and marches"),
        ("this+nation%27s+saving+grace", "this nation's saving grace"),
        ("500%25+more+man", "500% more man"),
        ("mm...food", "mm...food"),
        ("chomp+(remastered)", "chomp (remastered)"),
        ("lying+%2f+a+wooden+box", "lying / a wooden box"),
        ("y", "y"),
        ("frankjavcee+collection,+vol.+1,+pt.+ii", "frankjavcee collection, vol. 1, pt. ii"),
        ("public+image+ltd.", "public image ltd."),
    ],
)
def test_lastfm_format_to_user_details_format(user_torrent_str: str, expected: str) -> None:
    actual = lastfm_format_to_user_details_format(lastfm_format_str=user_torrent_str)
    assert (
        actual == expected
    ), f"Expected user_torrent_format_to_lastfm_format('{user_torrent_str}') to return '{expected}', but got '{actual}'"


def test_gather_red_user_details(valid_app_config: AppConfig) -> None:
    with patch("requests.Session.get", side_effect=mock_red_session_get_side_effect) as mock_sesh_get:
        release_searcher = ReleaseSearcher(app_config=valid_app_config)
        assert (
            release_searcher._red_user_details is None
        ), f"Expected ReleaseSearcher's initial value for _red_user_details attribute to be None, but got {type(release_searcher._red_user_details)}"
        release_searcher.gather_red_user_details()
        assert (
            release_searcher._red_user_details is not None
        ), f"Expected ReleaseSearcher's subsequent value for _red_user_details attribute after invoking 'gather_red_user_details' to not be None, but got {type(release_searcher._red_user_details)}"
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
    # TODO: mock the release_searcher._red_client attr
    # TODO: change this to use the new ReleaseSearcher method
    release_searcher = ReleaseSearcher(app_config=valid_app_config)
    release_searcher._red_format_preferences = mock_preference_ordering
    release_searcher._red_client.request_api = Mock(
        name="request_api",
        side_effect=[request.getfixturevalue(fixture_name)["response"] for fixture_name in mock_response_fixture_names],
    )
    actual_torrent_entry = release_searcher._search_red_release_by_preferences(
        artist_name="Fake+Artist",
        album_name="Fake+Release",
        release_type=RedReleaseType.ALBUM,
        first_release_year=1899,
    )
    assert actual_torrent_entry == expected_torrent_entry


@pytest.mark.parametrize(
    "use_release_type, use_first_release_year, use_record_label, use_catalog_number, found_te, expected_extra_search_args, expected",
    [
        (
            False,
            False,
            False,
            False,
            False,
            {
                "release_type": None,
                "first_release_year": None,
                "record_label": None,
                "catalog_number": None,
            },
            None,
        ),
        (
            False,
            False,
            False,
            False,
            True,
            {
                "release_type": None,
                "first_release_year": None,
                "record_label": None,
                "catalog_number": None,
            },
            ("https://redacted.sh/torrents.php?torrentid=69420", None),
        ),
        (
            True,
            False,
            False,
            False,
            False,
            {
                "release_type": RedReleaseType.ALBUM,
                "first_release_year": None,
                "record_label": None,
                "catalog_number": None,
            },
            None,
        ),
        (
            False,
            False,
            False,
            True,
            True,
            {
                "release_type": None,
                "first_release_year": None,
                "record_label": None,
                "catalog_number": "58010",
            },
            ("https://redacted.sh/torrents.php?torrentid=69420", "1234"),
        ),
        (
            False,
            False,
            True,
            False,
            True,
            {
                "release_type": None,
                "first_release_year": None,
                "record_label": "Get On Down",
                "catalog_number": None,
            },
            ("https://redacted.sh/torrents.php?torrentid=69420", "1234"),
        ),
        (
            False,
            True,
            False,
            False,
            True,
            {
                "release_type": None,
                "first_release_year": 2016,
                "record_label": None,
                "catalog_number": None,
            },
            ("https://redacted.sh/torrents.php?torrentid=69420", "1234"),
        ),
        (
            True,
            False,
            False,
            False,
            True,
            {
                "release_type": RedReleaseType.ALBUM,
                "first_release_year": None,
                "record_label": None,
                "catalog_number": None,
            },
            ("https://redacted.sh/torrents.php?torrentid=69420", "1234"),
        ),
        (
            True,
            True,
            True,
            True,
            False,
            {
                "release_type": RedReleaseType.ALBUM,
                "first_release_year": 2016,
                "record_label": "Get On Down",
                "catalog_number": "58010",
            },
            None,
        ),
        (
            True,
            True,
            True,
            True,
            True,
            {
                "release_type": RedReleaseType.ALBUM,
                "first_release_year": 2016,
                "record_label": "Get On Down",
                "catalog_number": "58010",
            },
            ("https://redacted.sh/torrents.php?torrentid=69420", "1234"),
        ),
    ],
)
def test_search_for_album_rec(
    use_release_type: bool,
    use_first_release_year: bool,
    use_record_label: bool,
    use_catalog_number: bool,
    found_te: bool,
    expected_extra_search_args: Dict[str, Any],
    expected: Optional[Tuple[str, Optional[str]]],
    mock_lfmai: LastFMAlbumInfo,
    mock_mbr: MBRelease,
    mock_best_te: TorrentEntry,
    valid_app_config: AppConfig,
    mock_red_user_details: RedUserDetails,
) -> None:
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
        release_searcher._resolve_last_fm_album_info = Mock(name="_resolve_last_fm_album_info")
        release_searcher._resolve_last_fm_album_info.return_value = mock_lfmai
        release_searcher._resolve_mb_release = Mock(name="_resolve_mb_release")
        release_searcher._resolve_mb_release.return_value = mock_mbr
        release_searcher._red_user_details = mock_red_user_details
        actual = release_searcher.search_for_album_rec(
            last_fm_rec=LastFMRec(
                lastfm_artist_str="Foo",
                lastfm_entity_str="Bar",
                recommendation_type=RecommendationType.ALBUM,
                rec_context=RecContext.SIMILAR_ARTIST,
            )
        )
        expected_rfp_search_kwargs = {
            **{
                "artist_name": "Foo",
                "album_name": "Bar",
            },
            **expected_extra_search_args,
        }
        if release_searcher._require_mbid_resolution:
            release_searcher._resolve_last_fm_album_info.assert_called_once()
            release_searcher._resolve_mb_release.assert_called_once_with(mbid=mock_lfmai.get_release_mbid())
        else:
            release_searcher._resolve_last_fm_album_info.assert_not_called()
            release_searcher._resolve_mb_release.assert_not_called()
        release_searcher._search_red_release_by_preferences.assert_called_once_with(**expected_rfp_search_kwargs)
        assert actual == expected, f"Expected result: {expected}, but got {actual}"


@pytest.mark.parametrize(
    "last_fm_artist_str, last_fm_album_str, expected_search_artist_str, expected_search_release_str",
    [
        (
            "Some+Artist",
            "Some+Album",
            "some artist",
            "some album",
        ),
        (
            "Some+Artist",
            "this+nation%27s+saving+grace",
            "some artist",
            "this nation's saving grace",
        ),
    ],
)
def test_search_for_album_rec_skip_prior_snatch(
    last_fm_artist_str: str,
    last_fm_album_str: str,
    expected_search_artist_str: str,
    expected_search_release_str: str,
    valid_app_config: AppConfig,
    mock_red_user_details: RedUserDetails,
) -> None:
    with patch.object(LastFMAlbumInfo, "construct_from_api_response") as mock_lfmai_class_method:
        with patch.object(MBRelease, "construct_from_api") as mock_mbr_class_method:
            with patch.object(ReleaseSearcher, "_search_red_release_by_preferences") as mock_rfp_search:
                release_searcher = ReleaseSearcher(app_config=valid_app_config)
                release_searcher._red_user_details = mock_red_user_details
                with patch.object(RedUserDetails, "has_snatched_release") as mock_rud_has_snatched_release:
                    mock_rud_has_snatched_release.return_value = True
                    actual_search_result = release_searcher.search_for_album_rec(
                        last_fm_rec=LastFMRec(
                            lastfm_artist_str=last_fm_artist_str,
                            lastfm_entity_str=last_fm_album_str,
                            recommendation_type=RecommendationType.ALBUM,
                            rec_context=RecContext.SIMILAR_ARTIST,
                        )
                    )
                    mock_rud_has_snatched_release.assert_called_once_with(
                        search_artist=expected_search_artist_str, search_release=expected_search_release_str
                    )
                    assert (
                        actual_search_result is None
                    ), f"Expected pre-snatched release to cause search_for_album_rec to return None, but got {actual_search_result}"


@pytest.mark.parametrize(
    "rec_context, allow_library_items, expected_result",
    [
        (RecContext.SIMILAR_ARTIST, False, ("https://redacted.sh/torrents.php?torrentid=123", None)),
        (RecContext.SIMILAR_ARTIST, True, ("https://redacted.sh/torrents.php?torrentid=123", None)),
        (RecContext.IN_LIBRARY, False, None),
        (RecContext.IN_LIBRARY, True, ("https://redacted.sh/torrents.php?torrentid=123", None)),
    ],
)
def test_search_for_album_rec_allow_library_items(
    rec_context: RecContext,
    allow_library_items: bool,
    expected_result: Optional[Tuple[str, Optional[str]]],
    valid_app_config: AppConfig,
) -> None:
    lfm_rec = LastFMRec(
        lastfm_artist_str="Some+Artist",
        lastfm_entity_str="Some+Album",
        recommendation_type=RecommendationType.ALBUM,
        rec_context=rec_context,
    )
    with patch.object(ReleaseSearcher, "_search_red_release_by_preferences") as mock_rfp_search:
        release_searcher = ReleaseSearcher(app_config=valid_app_config)
        release_searcher._skip_prior_snatches = False
        release_searcher._allow_library_items = allow_library_items
        release_searcher._require_mbid_resolution = False
        mock_rfp_search.return_value = TorrentEntry(
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
        )
        actual_result = release_searcher.search_for_album_rec(last_fm_rec=lfm_rec)
        assert (
            actual_result == expected_result
        ), f"Expected search result to be {expected_result} for allow_library_items set to {allow_library_items} and rec_context set to {rec_context}, but got {actual_result}"


# "in-library"
# "similar-artist"
@pytest.mark.parametrize(
    "last_fm_recs, mocked_search_results, expected_tsv_output_summary_rows",
    [
        ([], [], []),
        (
            [
                LastFMRec(
                    lastfm_artist_str="Some+Artist",
                    lastfm_entity_str="Their+Album",
                    recommendation_type=RecommendationType.ALBUM,
                    rec_context=RecContext.SIMILAR_ARTIST,
                )
            ],
            [None],
            [],
        ),
        (
            [
                LastFMRec(
                    lastfm_artist_str="Some+Artist",
                    lastfm_entity_str="Their+Album",
                    recommendation_type=RecommendationType.ALBUM,
                    rec_context=RecContext.SIMILAR_ARTIST,
                )
            ],
            [("https://redacted.sh/torrents.php?torrentid=69420", None)],
            [
                (
                    "album",
                    "similar-artist",
                    "https://www.last.fm/music/Some+Artist/Their+Album",
                    "https://redacted.sh/torrents.php?torrentid=69420",
                    "None",
                )
            ],
        ),
        (
            [
                LastFMRec(
                    lastfm_artist_str="Some+Artist",
                    lastfm_entity_str="Their+Album",
                    recommendation_type=RecommendationType.ALBUM,
                    rec_context=RecContext.SIMILAR_ARTIST,
                )
            ],
            [("https://redacted.sh/torrents.php?torrentid=69420", "some-fake-mbid-1234")],
            [
                (
                    "album",
                    "similar-artist",
                    "https://www.last.fm/music/Some+Artist/Their+Album",
                    "https://redacted.sh/torrents.php?torrentid=69420",
                    "some-fake-mbid-1234",
                )
            ],
        ),
        (
            [
                LastFMRec(
                    lastfm_artist_str="Some+Artist",
                    lastfm_entity_str="Their+Album",
                    recommendation_type=RecommendationType.ALBUM,
                    rec_context=RecContext.SIMILAR_ARTIST,
                ),
                LastFMRec(
                    lastfm_artist_str="Some+Other+Artist",
                    lastfm_entity_str="Some+Other+Album",
                    recommendation_type=RecommendationType.ALBUM,
                    rec_context=RecContext.IN_LIBRARY,
                ),
                LastFMRec(
                    lastfm_artist_str="Some+Bad+Artist",
                    lastfm_entity_str="Bad+Album",
                    recommendation_type=RecommendationType.ALBUM,
                    rec_context=RecContext.IN_LIBRARY,
                ),
            ],
            [
                ("https://redacted.sh/torrents.php?torrentid=69420", None),
                None,
                ("https://redacted.sh/torrents.php?torrentid=666", "some-fake-mbid-69"),
            ],
            [
                (
                    "album",
                    "similar-artist",
                    "https://www.last.fm/music/Some+Artist/Their+Album",
                    "https://redacted.sh/torrents.php?torrentid=69420",
                    "None",
                ),
                (
                    "album",
                    "in-library",
                    "https://www.last.fm/music/Some+Bad+Artist/Bad+Album",
                    "https://redacted.sh/torrents.php?torrentid=666",
                    "some-fake-mbid-69",
                ),
            ],
        ),
    ],
)
def test_search_for_album_recs(
    last_fm_recs: List[LastFMRec],
    mocked_search_results: List[Optional[Tuple[str, Optional[str]]]],
    expected_tsv_output_summary_rows: List[Tuple[str, ...]],
    valid_app_config: AppConfig,
    mock_red_user_details: RedUserDetails,
) -> None:
    search_res_q = deque(mocked_search_results)

    def mock_search_side_effect(*args, **kwargs) -> Optional[Tuple[str, Optional[str]]]:
        return search_res_q.popleft()

    with patch.object(ReleaseSearcher, "search_for_album_rec") as mock_search_for_album_rec:
        mock_search_for_album_rec.side_effect = mock_search_side_effect
        release_searcher = ReleaseSearcher(app_config=valid_app_config)
        release_searcher._red_user_details = release_searcher._red_user_details = mock_red_user_details
        release_searcher.search_for_album_recs(album_recs=last_fm_recs)
        actual_tsv_row_cnt = len(release_searcher._tsv_output_summary_rows)
        expected_tsv_row_cnt = len(expected_tsv_output_summary_rows)
        assert (
            actual_tsv_row_cnt == expected_tsv_row_cnt
        ), f"Expected {expected_tsv_row_cnt} tsv rows after searches, but got {actual_tsv_row_cnt} instead."
        for i, actual_row in enumerate(release_searcher._tsv_output_summary_rows):
            expected_row = expected_tsv_output_summary_rows[i]
            assert actual_row == expected_row, f"Expected row: {expected_row}, but got {actual_row}"


def test_search_for_album_recs_invalid_user_details(valid_app_config: AppConfig) -> None:
    with pytest.raises(ReleaseSearcherException, match="self._red_user_details has not yet been populated"):
        release_searcher = ReleaseSearcher(app_config=valid_app_config)
        release_searcher.search_for_album_recs(album_recs=[])


@pytest.mark.parametrize(
    "mock_instance_rows, expected_file_contents",
    [
        ([], [_EXPECTED_TSV_OUTPUT_HEADER]),
        (
            [
                (
                    "album",
                    "in-library",
                    "https://www.last.fm/music/Some+Bad+Artist/Bad+Album",
                    "https://redacted.sh/torrents.php?torrentid=666",
                    "some-fake-mbid-69",
                ),
            ],
            [
                _EXPECTED_TSV_OUTPUT_HEADER,
                "\t".join(
                    (
                        "album",
                        "in-library",
                        "https://www.last.fm/music/Some+Bad+Artist/Bad+Album",
                        "https://redacted.sh/torrents.php?torrentid=666",
                        "some-fake-mbid-69",
                    )
                )
                + "\n",
            ],
        ),
    ],
)
def test_write_output_summary_tsv(
    tmp_path: pytest.FixtureRequest,
    valid_app_config: AppConfig,
    mock_instance_rows: List[Tuple[str, ...]],
    expected_file_contents: List[str],
) -> None:
    test_out_filepath = os.path.join(tmp_path, "test_out.tsv")
    mocked_cli_options = {**valid_app_config._cli_options, **{"output_summary_filepath": test_out_filepath}}

    def _get_opt_side_effect(*args, **kwargs) -> Any:
        return mocked_cli_options[args[0]]

    with patch.object(AppConfig, "get_cli_option") as mock_app_conf_get_cli_option:
        mock_app_conf_get_cli_option.side_effect = _get_opt_side_effect
        with patch.object(ReleaseSearcher, "get_output_summary_rows") as mock_get_rows:
            mock_get_rows.return_value = mock_instance_rows
            release_searcher = ReleaseSearcher(app_config=valid_app_config)
            release_searcher.write_output_summary_tsv()
            assert os.path.exists(
                test_out_filepath
            ), f"Expected output summary tsv file ('{test_out_filepath}') does not exist"
            assert os.path.isfile(
                test_out_filepath
            ), f"Expected output summary tsv file ('{test_out_filepath}') is not of type file"
            expected_line_cnt = len(expected_file_contents)
            with open(test_out_filepath, "r") as f:
                actual_lines = f.readlines()
            actual_line_cnt = len(actual_lines)
            assert (
                actual_line_cnt == expected_line_cnt
            ), f"Expected {expected_line_cnt} lines in summary tsv output file but got {actual_line_cnt}"
            for i, actual_line in enumerate(actual_lines):
                expected_line = expected_file_contents[i]
                assert (
                    actual_line == expected_line
                ), f"Expected {i}th line to be '{expected_line}', but got '{actual_line}'"


@pytest.mark.parametrize(
    "mock_enable_snatches, mock_permalinks_to_snatch, expected_out_filenames, expected_request_params",
    [
        (False, [], [], []),
        (True, [], [], []),
        (
            False,
            ["https://redacted.sh/torrents.php?torrentid=69420", "https://redacted.sh/torrents.php?torrentid=666"],
            [],
            [],
        ),
        (
            True,
            ["https://redacted.sh/torrents.php?torrentid=69420", "https://redacted.sh/torrents.php?torrentid=666"],
            ["69420.torrent", "666.torrent"],
            ["id=69420", "id=666"],
        ),
    ],
)
def test_snatch_matches(
    tmp_path: pytest.FixtureRequest,
    valid_app_config: AppConfig,
    mock_enable_snatches: bool,
    mock_permalinks_to_snatch: List[str],
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
        with patch.object(RedAPIClient, "request_api") as mock_request_red_api:
            mock_request_red_api.return_value = bytes("fakedata", encoding="utf-8")
            expected_output_filepaths = [os.path.join(tmp_path, filename) for filename in expected_out_filenames]
            release_searcher = ReleaseSearcher(app_config=valid_app_config)
            release_searcher._permalinks_to_snatch = mock_permalinks_to_snatch
            release_searcher.snatch_matches()
            if not mock_enable_snatches:
                mock_request_red_api.assert_not_called()
                assert all([not tmp_filename.endswith(".torrent") for tmp_filename in os.listdir(tmp_path)])
            else:
                mock_request_red_api.assert_has_calls(
                    [
                        call(action="download", params=expected_request_param)
                        for expected_request_param in expected_request_params
                    ]
                )
                assert all([os.path.exists(out_filepath) for out_filepath in expected_output_filepaths])
