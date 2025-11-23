from contextlib import contextmanager
import copy
import csv
import json
import os

from sqlmodel import SQLModel, Session, StaticPool, create_engine

os.environ["PLASTERED_CONFIG"] = os.path.join(os.environ["APP_DIR"], "examples", "config.yaml")
import re
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
import yaml
from pytest_httpx import HTTPXMock

from plastered.config.app_settings import AppSettings, get_app_settings
from plastered.db.db_models import Result
from plastered.models.red_models import CdOnlyExtras, RedFormat
from plastered.models.types import EncodingEnum, EntityType, FormatEnum, MediaEnum
from plastered.run_cache.run_cache import CacheType, RunCache
from plastered.stats.stats import SkippedReason, SnatchFailureReason
from plastered.models.musicbrainz_models import MBRelease
from plastered.models.red_models import RedUserDetails

TEST_DIR_ABS_PATH = os.path.dirname(os.path.abspath(__file__))
PROJECT_ABS_PATH = os.path.abspath(os.getenv("APP_DIR"))
ROOT_MODULE_ABS_PATH = os.path.join(PROJECT_ABS_PATH, "plastered")

MOCK_RESOURCES_DIR_PATH = os.path.join(TEST_DIR_ABS_PATH, "resources")
MOCK_JSON_RESPONSES_DIR_PATH = os.path.join(MOCK_RESOURCES_DIR_PATH, "mock_api_responses")
MOCK_HTML_RESPONSES_DIR_PATH = os.path.join(MOCK_RESOURCES_DIR_PATH, "mock_browser_html")
INVALID_CONFIGS_DIR_PATH = os.path.join(MOCK_RESOURCES_DIR_PATH, "invalid_configs")
EXAMPLES_DIR_PATH = os.path.join(PROJECT_ABS_PATH, "examples")
_RED_MOCK_BROWSE_JSON_FILEPATH = os.path.join(MOCK_JSON_RESPONSES_DIR_PATH, "red_browse_api_response.json")
_RED_MOCK_BROWSE_EMPTY_JSON_FILEPATH = os.path.join(
    MOCK_JSON_RESPONSES_DIR_PATH, "red_browse_api_no_results_response.json"
)
_RED_MOCK_GROUP_JSON_FILEPATH = os.path.join(MOCK_JSON_RESPONSES_DIR_PATH, "mock_red_group_response.json")
_RED_MOCK_USER_STATS_JSON_FILEPATH = os.path.join(MOCK_JSON_RESPONSES_DIR_PATH, "red_userstats_response.json")
_RED_MOCK_USER_TORRENTS_SNATCHED_JSON_FILEPATH = os.path.join(
    MOCK_JSON_RESPONSES_DIR_PATH, "red_user_torrents_snatched_response.json"
)
_RED_MOCK_USER_TORRENTS_SEEDING_JSON_FILEPATH = os.path.join(
    MOCK_JSON_RESPONSES_DIR_PATH, "red_user_torrents_seeding_response.json"
)
_RED_MOCK_USER_JSON_FILEPATH = os.path.join(MOCK_JSON_RESPONSES_DIR_PATH, "red_user_response.json")
_LFM_MOCK_ALBUM_INFO_JSON_FILEPATH = os.path.join(MOCK_JSON_RESPONSES_DIR_PATH, "lfm_album_info_api_response.json")
_LFM_MOCK_TRACK_INFO_JSON_FILEPATH = os.path.join(MOCK_JSON_RESPONSES_DIR_PATH, "lfm_track_info_api_response.json")
# TODO: create this mock resource file + secret
_LFM_MOCK_TRACK_INFO_NO_ALBUM_JSON_FILEPATH = os.path.join(
    MOCK_JSON_RESPONSES_DIR_PATH, "lfm_track_info_no_album_api_response.json"
)
_MUSICBRAINZ_MOCK_RELEASE_JSON_FILEPATH = os.path.join(
    MOCK_JSON_RESPONSES_DIR_PATH, "musicbrainz_release_api_response.json"
)
_MUSICBRAINZ_MOCK_TRACK_ARID_JSON_FILEPATH = os.path.join(
    MOCK_JSON_RESPONSES_DIR_PATH, "mb_track_search_tuss_arid.json"
)
_MUSICBRAINZ_MOCK_RECORDING_TRACK_ARTIST_NAME_JSON_FILEPATH = os.path.join(
    MOCK_JSON_RESPONSES_DIR_PATH, "mb_track_search_tuss_artist_name.json"
)


# boilerplate for marking tests which should only run on release builds with the `--releasetests` flag
# https://docs.pytest.org/en/latest/example/simple.html#control-skipping-of-tests-according-to-command-line-option
def pytest_addoption(parser):
    parser.addoption(
        "--releasetests", action="store_true", default=False, help="run release tests in addition to standard tests"
    )
    parser.addoption(
        "--slowtests", action="store_true", default=False, help="run slow tests in addition to standard tests"
    )


def pytest_collection_modifyitems(config, items):
    # `True` when `--releasetests` provided in cli: do not skip release tests
    include_release_tests = config.getoption("--releasetests")
    # `True` when `--slowtests` provided in cli: do not skip slow tests
    include_slow_tests = config.getoption("--slowtests")
    skip_release = pytest.mark.skip(reason="--releasetests option required to run release tests")
    skip_slow = pytest.mark.skip(reason="--slowtests option required to run slow tests")
    for item in items:
        if "releasetest" in item.keywords and not include_release_tests:
            item.add_marker(skip_release)
        if "slow" in item.keywords and not include_slow_tests:
            item.add_marker(skip_slow)
        # https://pypi.org/project/pytest-httpx/#for-the-whole-test-suite
        # TODO: see if this can be removed
        item.add_marker(pytest.mark.httpx_mock(assert_all_responses_were_requested=False))


def load_mock_response_json(json_filepath: str) -> dict[str, Any]:
    """Utility function to load and return the mock API json blob located at the specified json_filepath."""
    with open(json_filepath) as f:
        json_data = json.load(f)
    return json_data


@pytest.fixture(scope="function")
def mock_session() -> Generator[Session, None, None]:
    """
    Creates a temporary in-memory session, following example here:
    https://sqlmodel.tiangolo.com/tutorial/fastapi/tests/?h=#pytest-fixtures
    """
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
        session.rollback()
        session.close()


@contextmanager
def mock_session_context() -> Generator[Session, None, None]:
    """
    Creates a temporary in-memory test session, following example in SQLModel docs,
    NOTE: This differs from the `mock_session` fixture in that this function can be used
    directly within a single unit test function, preventing weird concurrency issues with pytest-xdist
    which may lead to errors like 'sqlalchemy.exc.InvalidRequestError: Instance '<some ORM instance>' is not persistent within this Session'.
    """
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.rollback()
    session.close()


@pytest.fixture(scope="function")
def mock_track_result() -> Result:
    return Result(
        submit_timestamp=1759680000,
        is_manual=True,
        entity_type=EntityType.TRACK,
        artist="Some+Artist",
        entity="Some+Song",
    )


@pytest.fixture(scope="function")
def mock_album_result() -> Result:
    return Result(
        submit_timestamp=1759680000,
        is_manual=True,
        entity_type=EntityType.ALBUM,
        artist="Some+Artist",
        entity="Some+Album",
    )


@pytest.fixture(scope="session")
def mock_run_date_str() -> str:
    return "2025-01-20__00-24-42"


@pytest.fixture(scope="session")
def valid_config_filepath() -> str:
    return os.path.join(EXAMPLES_DIR_PATH, "config.yaml")


@pytest.fixture(scope="function")
def valid_config_filepath_function_scoped(valid_config_filepath: str) -> str:
    return str(valid_config_filepath)


@pytest.fixture(scope="session")
def minimal_valid_config_filepath() -> str:
    return os.path.join(EXAMPLES_DIR_PATH, "minimal_config.yaml")


@pytest.fixture(scope="session")
def valid_config_raw_data(valid_config_filepath: str) -> dict[str, Any]:
    with open(valid_config_filepath) as f:
        raw_config_data = yaml.safe_load(f.read())
    return raw_config_data


@pytest.fixture(scope="session")
def minimal_valid_config_raw_data(minimal_valid_config_filepath: str) -> dict[str, Any]:
    with open(minimal_valid_config_filepath) as f:
        raw_config_data = yaml.safe_load(f.read())
    return raw_config_data


@pytest.fixture(scope="session")
def minimal_valid_app_settings(minimal_valid_config_filepath: str) -> AppSettings:
    return get_app_settings(src_yaml_filepath=Path(minimal_valid_config_filepath))


@pytest.fixture(scope="session")
def mock_root_summary_dir_path(tmp_path_factory: pytest.FixtureRequest) -> Path:
    return tmp_path_factory.mktemp("summaries")


@pytest.fixture(scope="session")
def mock_output_summary_dir_path(mock_root_summary_dir_path: Path, mock_run_date_str: str) -> Path:
    run_summary_dir = mock_root_summary_dir_path / mock_run_date_str
    run_summary_dir.mkdir()
    return run_summary_dir


@pytest.fixture(scope="session")
def skipped_rows() -> list[list[str]]:
    return [
        ["album", "similar-artist", "Some Artist", "Their Album", "N/A", "69420", SkippedReason.ALREADY_SNATCHED.value],
        [
            "album",
            "similar-artist",
            "Some Other Artist",
            "Other Album",
            "N/A",
            "69420",
            SkippedReason.ABOVE_MAX_SIZE.value,
        ],
        ["album", "similar-artist", "Another Artist", "Fake Album", "N/A", "None", SkippedReason.NO_MATCH_FOUND.value],
        [
            "album",
            "in-library",
            "Another Artist",
            "Fake Album",
            "N/A",
            "None",
            SkippedReason.REC_CONTEXT_FILTERING.value,
        ],
        [
            "track",
            "in-library",
            "Another Artist",
            "Fake Release",
            "Some Track",
            "None",
            SkippedReason.REC_CONTEXT_FILTERING.value,
        ],
    ]


@pytest.fixture(scope="session")
def failed_snatch_rows() -> list[list[str]]:
    return [
        ["redacted.sh/torrents.php?torrentid=69", "abcde1-gfhe39", SnatchFailureReason.RED_API_REQUEST_ERROR.value],
        ["redacted.sh/torrents.php?torrentid=420", "asjh98uf2f-fajsdknau", SnatchFailureReason.FILE_ERROR.value],
        ["redacted.sh/torrents.php?torrentid=666", "ajdff2favdfvkj", SnatchFailureReason.OTHER.value],
    ]


@pytest.fixture(scope="session")
def snatch_summary_rows() -> list[list[str]]:
    return [
        [
            "album",
            "similar-artist",
            "Some Artist",
            "Their Album",
            "N/A",
            "69420",
            "Vinyl",
            "no",
            "/downloads/69420.torrent",
        ],
        ["album", "similar-artist", "Fake Band", "Fake Album", "N/A", "69", "CD", "yes", "/downloads/69.torrent"],
        [
            "track",
            "similar-artist",
            "Fake Band",
            "Fake Album",
            "Fake Song",
            "420",
            "CD",
            "yes",
            "/downloads/420.torrent",
        ],
    ]


@pytest.fixture(scope="session")
def mock_summary_tsvs(
    mock_output_summary_dir_path: Path,
    failed_snatch_rows: list[list[str]],
    skipped_rows: list[list[str]],
    snatch_summary_rows: list[list[str]],
) -> dict[str, str]:
    type_to_headers = {
        "failed": ["RED_permalink", "Matched_MBID_(if_any)", "Failure_reason"],
        "snatched": [
            "Type",
            "LFM_Rec_context",
            "Artist",
            "Release",
            "Track_Rec",
            "RED_tid",
            "Media",
            "FL_token_used",
            "Snatch_path",
        ],
        "skipped": ["Type", "LFM_Rec_context", "Artist", "Release", "Track_Rec", "Matched_RED_TID", "Skip_reason"],
    }

    def _write_dummy_tsv(dummy_path: str, header: list[str], dummy_rows: list[list[str]]) -> None:
        with open(dummy_path, "w") as f:
            w = csv.writer(f, delimiter="\t", lineterminator="\n")
            w.writerow(header)
            w.writerows(dummy_rows)

    failed_tsv_path = os.path.join(mock_output_summary_dir_path, "failed.tsv")
    snatched_tsv_path = os.path.join(mock_output_summary_dir_path, "snatched.tsv")
    skipped_tsv_path = os.path.join(mock_output_summary_dir_path, "skipped.tsv")
    _write_dummy_tsv(failed_tsv_path, type_to_headers["failed"], failed_snatch_rows)
    _write_dummy_tsv(snatched_tsv_path, type_to_headers["snatched"], snatch_summary_rows)
    _write_dummy_tsv(skipped_tsv_path, type_to_headers["skipped"], skipped_rows)
    return {"failed": failed_tsv_path, "snatched": snatched_tsv_path, "skipped": skipped_tsv_path}


@pytest.fixture(scope="session")
def mock_action_to_red_json_responses() -> dict[str, dict[str, Any]]:
    return {"browse": load_mock_response_json(json_filepath=_RED_MOCK_BROWSE_JSON_FILEPATH)}


@pytest.fixture(scope="session")
def mock_red_browse_non_empty_response() -> dict[str, Any]:
    return load_mock_response_json(json_filepath=_RED_MOCK_BROWSE_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_red_browse_empty_response() -> dict[str, Any]:
    return load_mock_response_json(json_filepath=_RED_MOCK_BROWSE_EMPTY_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_red_group_response() -> dict[str, Any]:
    return load_mock_response_json(json_filepath=_RED_MOCK_GROUP_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_red_user_stats_response() -> dict[str, Any]:
    return load_mock_response_json(json_filepath=_RED_MOCK_USER_STATS_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_red_user_torrents_snatched_response() -> dict[str, Any]:
    return load_mock_response_json(json_filepath=_RED_MOCK_USER_TORRENTS_SNATCHED_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_red_user_torrents_seeding_response() -> dict[str, Any]:
    return load_mock_response_json(json_filepath=_RED_MOCK_USER_TORRENTS_SEEDING_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_red_user_response() -> dict[str, Any]:
    return load_mock_response_json(json_filepath=_RED_MOCK_USER_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_red_user_details(
    mock_red_user_torrents_snatched_response: dict[str, Any],
    mock_red_user_torrents_seeding_response: dict[str, Any],
    mock_red_user_response: dict[str, Any],
) -> RedUserDetails:
    return RedUserDetails(
        user_id=69,
        snatched_count=5216,
        snatched_torrents_list=mock_red_user_torrents_snatched_response["response"]["snatched"]
        + mock_red_user_torrents_seeding_response["response"]["seeding"],
        user_profile_json=mock_red_user_response["response"],
    )


@pytest.fixture(scope="function")
def mock_red_user_details_fn_scoped(mock_red_user_details: RedUserDetails) -> RedUserDetails:
    """Same contents as the session-scoped one above, but function-scoped to allow for per-test attribute overrides."""
    return RedUserDetails(
        user_id=mock_red_user_details.user_id,
        snatched_count=mock_red_user_details.snatched_count,
        snatched_torrents_list=copy.deepcopy(mock_red_user_details.snatched_torrents_list),
        user_profile_json=copy.deepcopy(mock_red_user_details.user_profile_json),
    )


@pytest.fixture(scope="session")
def mock_lfm_album_info_json() -> dict[str, Any]:
    return load_mock_response_json(json_filepath=_LFM_MOCK_ALBUM_INFO_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_full_lfm_track_info_json() -> dict[str, Any]:
    return load_mock_response_json(json_filepath=_LFM_MOCK_TRACK_INFO_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_no_album_lfm_track_info_json() -> dict[str, Any]:
    return load_mock_response_json(json_filepath=_LFM_MOCK_TRACK_INFO_NO_ALBUM_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_lfm_track_info_raise_client_exception() -> dict[str, Any]:
    return {"error": "should-raise-LFMClientException"}


@pytest.fixture(scope="session")
def mock_musicbrainz_release_json() -> dict[str, Any]:
    return load_mock_response_json(json_filepath=_MUSICBRAINZ_MOCK_RELEASE_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_musicbrainz_track_search_arid_json() -> dict[str, Any]:
    return load_mock_response_json(json_filepath=_MUSICBRAINZ_MOCK_TRACK_ARID_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_musicbrainz_track_search_artist_name_json() -> dict[str, Any]:
    return load_mock_response_json(json_filepath=_MUSICBRAINZ_MOCK_RECORDING_TRACK_ARTIST_NAME_JSON_FILEPATH)


@pytest.fixture(scope="session")
def mock_musicbrainz_track_search_no_release_name_json() -> dict[str, Any]:
    raw_data = load_mock_response_json(json_filepath=_MUSICBRAINZ_MOCK_RECORDING_TRACK_ARTIST_NAME_JSON_FILEPATH)
    del raw_data["recordings"][0]["releases"][0]["title"]
    return raw_data


@pytest.fixture(scope="session")
def expected_mb_release() -> MBRelease:
    return MBRelease(
        mbid="d211379d-3203-47ed-a0c5-e564815bb45a",
        title="Dr. Octagonecologyst",
        artist="Dr. Octagon",
        primary_type="Album",
        first_release_year=1996,
        release_date="2017-05-19",
        label="Get On Down",
        catalog_number="58010",
        release_group_mbid="b38e21f6-8f76-3f87-a021-e91afad9e7e5",
    )


@pytest.fixture(scope="session")
def cache_root_dir_path(tmp_path_factory: pytest.FixtureRequest) -> Path:
    """
    Fixture which creates a session-scoped temporary root cache directory and returns the pathlib.Path object for it.
    """
    return tmp_path_factory.mktemp("cache")


@pytest.fixture(scope="session")
def api_cache_dir_path(cache_root_dir_path: Path) -> Path:
    """
    Fixture which creates a session-scoped API cache directory and returns the pathlib.Path object for it.
    """
    api_cache_path = cache_root_dir_path / "api"
    api_cache_path.mkdir()
    return api_cache_path


@pytest.fixture(scope="session")
def scraper_cache_dir_path(cache_root_dir_path: Path) -> Path:
    """
    Fixture which creates a session-scoped Scraper cache directory and returns the pathlib.Path object for it.
    """
    scraper_cache_path = cache_root_dir_path / "scraper"
    scraper_cache_path.mkdir()
    return scraper_cache_path


# @pytest.fixture(scope="function")
# def valid_app_settings(valid_config_filepath: str, valid_config_envvar, cache_root_dir_path: Path) -> AppSettings:
#     """
#     Function-scoped valid AppConfig fixture, with cache root dir
#     overridden to use the session-scoped tmp cache root dir fixture
#     """
#     valid_path = Path(valid_config_filepath)
#     with patch("plastered.config.app_settings.get_config_path", return_value=valid_path):
#         app_settings = get_app_settings(src_yaml_filepath=valid_path)
#         # app_config._base_cache_directory_path = str(cache_root_dir_path)
#         yield app_settings


@pytest.fixture(scope="function")
def valid_app_settings(valid_config_filepath: str, cache_root_dir_path: Path) -> AppSettings:
    """
    Function-scoped valid `AppSettings` fixture, with cache root dir
    overridden to use the session-scoped tmp cache root dir fixture
    """
    app_settings = get_app_settings(valid_config_filepath, cli_overrides=dict())
    app_settings._base_cache_directory_path = str(cache_root_dir_path)
    return app_settings


@pytest.fixture(scope="session")
def api_run_cache(valid_config_filepath: str) -> RunCache:
    app_settings = get_app_settings(src_yaml_filepath=Path(valid_config_filepath))
    return RunCache(app_settings=app_settings, cache_type=CacheType.API)


@pytest.fixture(scope="function")
def enabled_api_run_cache(api_run_cache: RunCache) -> RunCache:
    """
    Function-scoped fixture which consumes the session-scoped api_run_cache fixture, and
    clears the state to ensure the cache is not altered by unrelated tests.
    """
    api_run_cache._enabled = True
    api_run_cache.clear()
    return api_run_cache


@pytest.fixture(scope="session")
def scraper_run_cache(valid_config_filepath: str) -> RunCache:
    app_settings = get_app_settings(src_yaml_filepath=Path(valid_config_filepath))
    return RunCache(app_settings=app_settings, cache_type=CacheType.SCRAPER)


def mock_red_snatch_get_side_effect() -> bytes:
    resp_mock = MagicMock()
    resp_mock.content.return_value = bytes("fakebytes", encoding="utf-8")
    resp_mock.status_code.return_value = 200
    return resp_mock


# -def mock_lfm_session_get_side_effect(*args, **kwargs) -> dict[str, Any]:
# -    """
# -    Helper test function to pass as the value for any
# -    patch('requests.Session.get', ...) mocks on a LFMAPIClient test case.
# -    This ensures that the subsequent response's json() value is properly overridden with the desired data.
# -    """
# -    url_val = kwargs["url"]
# -    # resp_mock = MagicMock(name="json")
# -    mock_json = None
# -    if "album.getinfo" in url_val:
# -        mock_json = load_mock_response_json(json_filepath=_LFM_MOCK_ALBUM_INFO_JSON_FILEPATH)
# -    elif "track.getinfo" in url_val:
# -        mock_json = load_mock_response_json(json_filepath=_LFM_MOCK_TRACK_INFO_JSON_FILEPATH)
# -    resp_mock = MagicMock()
# -    resp_mock.json.return_value = mock_json
# -    # nonsense mock magic to work with mocking properties AND methods: https://stackoverflow.com/a/42637101
# -    type(resp_mock).status_code = PropertyMock(return_value=200)
# -    return resp_mock


# -def mock_red_session_get_side_effect(*args, **kwargs) -> dict[str, Any]:
# -    """
# -    Helper test function to pass as the value for any
# -    patch('requests.Session.get', ...) mocks on a RedAPIClient test case.
# -    This ensures that the subsequent response's json()/content value is properly overridden with the desired data.
# -    """
# -    _red_actions_to_mock_json = {
# -        "browse": load_mock_response_json(json_filepath=_RED_MOCK_BROWSE_JSON_FILEPATH),
# -        "torrentgroup": load_mock_response_json(json_filepath=_RED_MOCK_GROUP_JSON_FILEPATH),
# -        "community_stats": load_mock_response_json(json_filepath=_RED_MOCK_USER_STATS_JSON_FILEPATH),
# -        "user_torrents": {
# -            "snatched": load_mock_response_json(json_filepath=_RED_MOCK_USER_TORRENTS_SNATCHED_JSON_FILEPATH),
# -            "seeding": load_mock_response_json(json_filepath=_RED_MOCK_USER_TORRENTS_SEEDING_JSON_FILEPATH),
# -        },
# -    }
# -    url_val = kwargs["url"]
# -    m = re.match(r"^.*\?action=([^&]+)&.*", url_val)
# -    red_action = m.groups()[0]
# -    if red_action == "user_torrents":
# -        key = "snatched" if "type=snatched" in kwargs["url"] else "seeding"
# -        mock_json = _red_actions_to_mock_json[red_action][key]
# -    else:
# -        mock_json = _red_actions_to_mock_json[red_action]
# -    resp_mock = MagicMock(name="json")
# -    resp_mock.json.return_value = mock_json
# -    resp_mock.status_code.return_value = 200
# -    return resp_mock


def mock_mb_session_get_side_effect(*args, **kwargs) -> dict[str, Any]:
    """
    Helper test function to pass as the value for any
    patch('requests.Session.get', ...) mocks on a MusicBrainzAPIClient test case.
    This ensures that the subsequent response's json() value is properly overridden with the desired data.
    """
    resp_mock = MagicMock(name="json")
    mock_json = load_mock_response_json(json_filepath=_MUSICBRAINZ_MOCK_RELEASE_JSON_FILEPATH)
    resp_mock.json.return_value = mock_json
    return resp_mock


@pytest.fixture(scope="session")
def expected_red_format_list() -> list[RedFormat]:
    return [
        RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.SACD),
        RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
        RedFormat(
            format=FormatEnum.FLAC,
            encoding=EncodingEnum.LOSSLESS,
            media=MediaEnum.CD,
            cd_only_extras=CdOnlyExtras(log=100, has_cue=True),
        ),
        RedFormat(
            format=FormatEnum.FLAC,
            encoding=EncodingEnum.LOSSLESS,
            media=MediaEnum.CD,
            cd_only_extras=CdOnlyExtras(log=100, has_cue=False),
        ),
        RedFormat(
            format=FormatEnum.FLAC,
            encoding=EncodingEnum.LOSSLESS,
            media=MediaEnum.CD,
            cd_only_extras=CdOnlyExtras(log=0, has_cue=False),
        ),
        RedFormat(format=FormatEnum.MP3, encoding=EncodingEnum.MP3_V0, media=MediaEnum.ANY),
    ]


def mock_lfm_client_callback(request: httpx.Request) -> httpx.Response:
    """
    Callback function used by the global_httpx_mock fixture (defined below) for any
    unit tests which run HTTP calls to the LFM api.
    """
    lfm_actions_to_mock_json = {
        "album.getinfo": load_mock_response_json(json_filepath=_LFM_MOCK_ALBUM_INFO_JSON_FILEPATH),
        "track.getinfo": load_mock_response_json(json_filepath=_LFM_MOCK_TRACK_INFO_JSON_FILEPATH),
    }
    m = re.match(r"^.*\?.*method=(album\.getinfo|track\.getinfo).*$", str(request.url))
    lfm_action = m.groups()[0]
    mock_json = lfm_actions_to_mock_json[lfm_action]
    return httpx.Response(status_code=200, json=mock_json)


def mock_musicbrainz_client_callback(request: httpx.Request) -> httpx.Response:
    """
    Callback function used by the global_httpx_mock fixture (defined below) for any
    unit tests which run HTTP calls to the musicbrainz api.
    """
    mb_endpoints_to_mock_json = {
        "release": load_mock_response_json(json_filepath=_MUSICBRAINZ_MOCK_RELEASE_JSON_FILEPATH),
        "recording": load_mock_response_json(json_filepath=_MUSICBRAINZ_MOCK_RECORDING_TRACK_ARTIST_NAME_JSON_FILEPATH),
    }
    # "https://musicbrainz.org/ws/2/" + "(release|recording)/.*"
    url_val = str(request.url)
    m = re.match(r"^.*musicbrainz\.org/ws/2/(release|recording)/.*", url_val)
    mb_endpoint = m.groups()[0]
    mock_json = mb_endpoints_to_mock_json[mb_endpoint]
    return httpx.Response(status_code=200, json=mock_json)


@pytest.fixture(scope="session")
def red_url_regex_to_mock_json(
    mock_red_browse_non_empty_response: dict[str, Any],
    mock_red_group_response: dict[str, Any],
    mock_red_user_stats_response: dict[str, Any],
    mock_red_user_torrents_snatched_response: dict[str, Any],
    mock_red_user_torrents_seeding_response: dict[str, Any],
    mock_red_user_response: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """
    Utility fixture consumed by `global_httpx_mock` to map RED API url patterns to mock JSON response payloads
    """
    return [
        (r"^https://redacted\.sh/ajax\.php\?action=browse.*$", mock_red_browse_non_empty_response),
        (r"^https://redacted\.sh/ajax\.php\?action=torrentgroup.*$", mock_red_group_response),
        (r"^https://redacted\.sh/ajax\.php\?action=community_stats.*$", mock_red_user_stats_response),
        # ?action=user_torrents&type=snatched&...
        (
            r"^https://redacted\.sh/ajax\.php\?action=user_torrents.*type=snatched.*$",
            mock_red_user_torrents_snatched_response,
        ),
        # ?action=user_torrents&... WITHOUT `type=snatched` appearing in the request url
        (
            r"^https://redacted\.sh/ajax\.php\?action=user_torrents.*(?!.*type=snatched).*$",
            mock_red_user_torrents_seeding_response,
        ),
        # action=user& endpoint (not to be confused with user_torrents endpoint)
        (r"^https://redacted\.sh/ajax\.php\?action=user\&.*$", mock_red_user_response),
    ]


@pytest.fixture(scope="session")
def lfm_url_regex_to_mock_json(
    mock_lfm_album_info_json: dict[str, Any], mock_full_lfm_track_info_json: dict[str, Any]
) -> list[tuple[str, dict[str, Any]]]:
    """
    Utility fixture consumed by `global_httpx_mock` to map LFM API url patterns to mock JSON response payloads.
    """
    return [
        (r"^https://ws\.audioscrobbler\.com/2\.0/\?method=album\.getinfo.*$", mock_lfm_album_info_json),
        (r"^https://ws\.audioscrobbler\.com/2\.0/\?method=track\.getinfo.*$", mock_full_lfm_track_info_json),
    ]


@pytest.fixture(scope="session")
def mb_url_regex_to_mock_json(
    mock_musicbrainz_release_json: dict[str, Any],
    mock_musicbrainz_track_search_arid_json: dict[str, Any],
    mock_musicbrainz_track_search_artist_name_json: dict[str, Any],
) -> list[tuple[str, str]]:
    """
    Utility fixture consumed by `global_httpx_mock` to map MB API url patterns to mock JSON response payloads.
    """
    return [
        (r"https://musicbrainz\.org/ws/2/release/.*$", mock_musicbrainz_release_json),
        (
            r"https://musicbrainz\.org/ws/2/recording\?query=.*recording:.+AND.+arid:.*$",
            mock_musicbrainz_track_search_arid_json,
        ),
        (
            r"https://musicbrainz\.org/ws/2/recording\?query=.*recording:.+AND.+artist:.*$",
            mock_musicbrainz_track_search_artist_name_json,
        ),
    ]


@pytest.fixture(scope="function", autouse=True)
def global_httpx_mock(
    request: pytest.FixtureRequest,
    httpx_mock: HTTPXMock,
    red_url_regex_to_mock_json: list[tuple[str, dict[str, Any]]],
    lfm_url_regex_to_mock_json: list[tuple[str, dict[str, Any]]],
    mb_url_regex_to_mock_json: list[tuple[str, dict[str, Any]]],
) -> Generator[HTTPXMock, Any, Any]:
    """
    Globally applied fixture to ensure no HTTP requests in the unit tests
    leak out to the actual network. via pytest-httpx:  https://pypi.org/project/pytest-httpx/
    """
    # Do not add any expected responses to this fixture for the edge-case tests which need to run with their own
    # function-specific mock responses. https://stackoverflow.com/a/38763328
    if "override_global_httpx_mock" in request.keywords:
        yield httpx_mock
    else:
        for red_regex_and_json in red_url_regex_to_mock_json:
            request_url_pattern, resp_mock_json = red_regex_and_json
            httpx_mock.add_response(
                url=re.compile(request_url_pattern), json=resp_mock_json, is_optional=True, is_reusable=True
            )
        for lfm_regex_and_json in lfm_url_regex_to_mock_json:
            request_url_pattern, resp_mock_json = lfm_regex_and_json
            httpx_mock.add_response(
                url=re.compile(request_url_pattern), json=resp_mock_json, is_optional=True, is_reusable=True
            )
        for mb_regex_and_json in mb_url_regex_to_mock_json:
            request_url_pattern, resp_mock_json = mb_regex_and_json
            httpx_mock.add_response(
                url=re.compile(request_url_pattern), json=resp_mock_json, is_optional=True, is_reusable=True
            )
        yield httpx_mock
