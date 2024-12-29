from typing import List
from unittest.mock import patch

import pytest

from lastfm_recs_scraper.config.config_parser import AppConfig
from lastfm_recs_scraper.scraper.lastfm_recs_scraper import (
    LastFMRec,
    LastFMRecsScraper,
    RecContext,
    RecommendationType,
)
from lastfm_recs_scraper.utils.constants import CHROMEDRIVER_EXECUTABLE_PATH
from tests.conftest import valid_app_config
from tests.scraper_tests.conftest import (
    album_recs_page_one_html,
    login_page_html,
    track_recs_page_one_html,
)


@pytest.fixture(scope="function")
def lfm_rec_scraper(valid_app_config: AppConfig) -> LastFMRecsScraper:
    return LastFMRecsScraper(app_config=valid_app_config)


# TODO: add a similar expected_track_recs fixture
@pytest.fixture(scope="session")
def expected_album_recs() -> List[LastFMRec]:
    return [
        LastFMRec(
            lastfm_artist_str="Dr.+Octagon",
            lastfm_entity_str="Dr.+Octagonecologyst",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Soulwax",
            lastfm_entity_str="Much+Against+Everyone%27s+Advice",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
        LastFMRec(
            lastfm_artist_str="Mission+of+Burma",
            lastfm_entity_str="Signals,+Calls+and+Marches",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="The+Fall",
            lastfm_entity_str="This+Nation%27s+Saving+Grace",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Bo+Diddley",
            lastfm_entity_str="500%25+More+Man",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
        LastFMRec(
            lastfm_artist_str="MF+DOOM",
            lastfm_entity_str="MM...FOOD",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
        LastFMRec(
            lastfm_artist_str="Black+Moth+Super+Rainbow",
            lastfm_entity_str="Dandelion+Gum",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
        LastFMRec(
            lastfm_artist_str="Magazine",
            lastfm_entity_str="Real+Life",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Red+Rider",
            lastfm_entity_str="Neruda",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
        LastFMRec(
            lastfm_artist_str="Pylon",
            lastfm_entity_str="Chomp+(Remastered)",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Thee+Oh+Sees",
            lastfm_entity_str="Floating+Coffin",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Minutemen",
            lastfm_entity_str="Double+Nickels+on+the+Dime",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Ty+Segall+Band",
            lastfm_entity_str="Slaughterhouse",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Television",
            lastfm_entity_str="Marquee+Moon",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Factory+Floor",
            lastfm_entity_str="Lying+%2F+A+Wooden+Box",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
        LastFMRec(
            lastfm_artist_str="Donovan",
            lastfm_entity_str="Sunshine+Superman",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
        LastFMRec(
            lastfm_artist_str="The+Pop+Group",
            lastfm_entity_str="Y",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="FrankJavCee",
            lastfm_entity_str="FrankJavCee+Collection,+Vol.+1,+Pt.+II",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
        LastFMRec(
            lastfm_artist_str="Public+Image+Ltd.",
            lastfm_entity_str="Metal+Box",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Wire",
            lastfm_entity_str="Chairs+Missing",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
    ]


def test_scraper_init(lfm_rec_scraper: LastFMRecsScraper, valid_app_config: AppConfig) -> None:
    with patch.object(LastFMRecsScraper, "__enter__") as enter_method_mock:
        enter_method_mock.assert_not_called()
    with patch.object(LastFMRecsScraper, "__exit__") as exit_method_mock:
        exit_method_mock.assert_not_called()
    expected_username = valid_app_config.get_cli_option("last_fm_username")
    actual_username = lfm_rec_scraper._last_fm_username
    assert (
        actual_username == expected_username
    ), f"Unexpected username in LastFMRecsScraper instance: '{actual_username}'. Expected: '{expected_username}'"
    expected_password = valid_app_config.get_cli_option("last_fm_password")
    actual_password = lfm_rec_scraper._last_fm_password
    assert (
        actual_password == expected_password
    ), f"Unexpected password in LastFMRecsScraper instance: '{actual_password}'. Expected: '{expected_password}'"
    expected_is_logged_in = False
    actual_is_logged_in = lfm_rec_scraper._is_logged_in
    assert (
        actual_is_logged_in == expected_is_logged_in
    ), f"Expected LastFMRecsScraper instance's _is_logged_in field to be False up __init__ call, but was {actual_is_logged_in}"
    expected_driver_opts = [
        "--no-sandbox",
        "--headless",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--user-data-dir=/tmp/chrome",
    ]
    actual_driver_opts = lfm_rec_scraper._chrome_driver_options.arguments
    assert (
        actual_driver_opts == expected_driver_opts
    ), f"Unexpected chrome driver options in LastFMRecsScraper instance. Got {actual_driver_opts}, expected: {expected_driver_opts}"


def test_scraper_enter(lfm_rec_scraper: LastFMRecsScraper) -> None:
    with patch("selenium.webdriver.ChromeService") as chrome_service_mock:
        with patch("selenium.webdriver.Chrome") as chrome_driver_mock:
            with patch("selenium.webdriver.support.wait.WebDriverWait") as webdriver_wait_mock:
                with patch.object(LastFMRecsScraper, "_user_login") as user_login_mock:
                    lfm_rec_scraper.__enter__()
                    chrome_service_mock.assert_called_once_with(executable_path=CHROMEDRIVER_EXECUTABLE_PATH, port=4444)
                    chrome_driver_mock.assert_called_once_with(
                        options=lfm_rec_scraper._chrome_driver_options, service=chrome_service_mock.return_value
                    )
                    # TODO (later): figure out why the webdriver_wait_mock.assert_called() functions dont' work here.
                    assert hasattr(lfm_rec_scraper, "_wait")
                    user_login_mock.assert_called_once()


def test_scraper_exit(lfm_rec_scraper: LastFMRecsScraper) -> None:
    with patch("selenium.webdriver.ChromeService") as chrome_service_mock:
        with patch("selenium.webdriver.Chrome") as chrome_driver_mock:
            with patch("selenium.webdriver.support.wait.WebDriverWait") as webdriver_wait_mock:
                with patch.object(LastFMRecsScraper, "_user_login") as user_login_mock:
                    with patch.object(LastFMRecsScraper, "_user_logout") as user_logout_mock:
                        lfm_rec_scraper.__enter__()
                        lfm_rec_scraper.__exit__()
                        user_logout_mock.assert_called_once
                        lfm_rec_scraper._driver.quit.assert_called_once()


def test_context_manager(valid_app_config: AppConfig) -> None:
    with patch.object(LastFMRecsScraper, "__enter__") as enter_mock:
        with patch.object(LastFMRecsScraper, "__exit__") as exit_mock:
            with LastFMRecsScraper(app_config=valid_app_config) as ctx_rec_mgr:
                enter_mock.assert_called_once()
                exit_mock.assert_not_called()
            enter_mock.assert_called_once()
            exit_mock.assert_called_once()


# TODO: add a similar test_extract_track_recs_from_page_source test
def test_extract_album_recs_from_page_source(
    album_recs_page_one_html: str, lfm_rec_scraper: LastFMRecsScraper, expected_album_recs: List[LastFMRec]
) -> None:
    actual_recs_list = lfm_rec_scraper._extract_recs_from_page_source(
        page_source=album_recs_page_one_html, rec_type=RecommendationType.ALBUM
    )
    expected_length = len(expected_album_recs)
    actual_length = len(actual_recs_list)
    assert actual_length == expected_length, f"Expected {expected_length} album recs, but got {actual_length}."
    for i, actual_rec in enumerate(actual_recs_list):
        expected_rec = expected_album_recs[i]
        assert (
            actual_rec == expected_rec
        ), f"Expected {i}'th rec to be '{str(expected_rec)}' but got '{str(actual_rec)}'"


# TODO: add scrape_recs_list method test(s)
