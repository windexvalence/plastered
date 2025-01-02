import os
from collections import deque
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import call, patch

import pytest

from lastfm_recs_scraper.config.config_parser import AppConfig
from lastfm_recs_scraper.release_search.release_searcher import (
    ReleaseSearcher,
    require_mbid_resolution,
)
from lastfm_recs_scraper.scraper.lastfm_recs_scraper import (
    LastFMRec,
    RecContext,
    RecommendationType,
)
from lastfm_recs_scraper.utils.lastfm_utils import LastFMAlbumInfo
from lastfm_recs_scraper.utils.musicbrainz_utils import MBRelease
from lastfm_recs_scraper.utils.red_utils import (
    RedFormatPreferences,
    RedReleaseType,
    TorrentEntry,
)
from tests.conftest import valid_app_config

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
        with patch.object(LastFMAlbumInfo, "construct_from_api_response") as mock_lfmai_class_method:
            with patch.object(MBRelease, "construct_from_api") as mock_mbr_class_method:
                with patch.object(RedFormatPreferences, "search_release_by_preferences") as mock_rfp_search:
                    mock_lfmai_class_method.return_value = mock_lfmai
                    mock_mbr_class_method.return_value = mock_mbr
                    mock_rfp_search.return_value = mock_best_te if found_te else None
                    actual = release_searcher.search_for_album_rec(
                        last_fm_artist_str="Foo",
                        last_fm_album_str="Bar",
                    )
                    expected_rfp_search_kwargs = {
                        **{
                            "red_client": release_searcher._red_client,
                            "artist_name": "Foo",
                            "album_name": "Bar",
                        },
                        **expected_extra_search_args,
                    }
                    if release_searcher._require_mbid_resolution:
                        mock_lfmai_class_method.assert_called_once()
                        mock_mbr_class_method.assert_called_once_with(
                            musicbrainz_client=release_searcher._musicbrainz_client,
                            mbid=mock_lfmai.get_release_mbid(),
                        )
                    else:
                        mock_lfmai_class_method.assert_not_called()
                        mock_mbr_class_method.assert_not_called()
                    mock_rfp_search.assert_called_once_with(**expected_rfp_search_kwargs)
                    assert actual == expected, f"Expected result: {expected}, but got {actual}"


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
) -> None:
    search_res_q = deque(mocked_search_results)

    def mock_search_side_effect(*args, **kwargs) -> Optional[Tuple[str, Optional[str]]]:
        return search_res_q.popleft()

    with patch.object(ReleaseSearcher, "search_for_album_rec") as mock_search_for_album_rec:
        mock_search_for_album_rec.side_effect = mock_search_side_effect
        release_searcher = ReleaseSearcher(app_config=valid_app_config)
        release_searcher.search_for_album_recs(album_recs=last_fm_recs)
        actual_tsv_row_cnt = len(release_searcher._tsv_output_summary_rows)
        expected_tsv_row_cnt = len(expected_tsv_output_summary_rows)
        assert (
            actual_tsv_row_cnt == expected_tsv_row_cnt
        ), f"Expected {expected_tsv_row_cnt} tsv rows after searches, but got {actual_tsv_row_cnt} instead."
        for i, actual_row in enumerate(release_searcher._tsv_output_summary_rows):
            expected_row = expected_tsv_output_summary_rows[i]
            assert actual_row == expected_row, f"Expected row: {expected_row}, but got {actual_row}"


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
        **{"snatch_reqs": mock_enable_snatches, "snatch_directory": tmp_path},
    }

    def _get_opt_side_effect(*args, **kwargs) -> Any:
        return mocked_cli_options[args[0]]

    with patch.object(AppConfig, "get_cli_option") as mock_app_conf_get_cli_option:
        mock_app_conf_get_cli_option.side_effect = _get_opt_side_effect
        with patch("lastfm_recs_scraper.release_search.release_searcher.request_red_api") as mock_request_red_api:
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
                        call(red_client=release_searcher._red_client, action="download", params=expected_request_param)
                        for expected_request_param in expected_request_params
                    ]
                )
                assert all([os.path.exists(out_filepath) for out_filepath in expected_output_filepaths])
