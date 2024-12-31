import re
from typing import List
from unittest.mock import MagicMock, call, patch

import pytest
from rebrowser_playwright.sync_api import PlaywrightContextManager

from lastfm_recs_scraper.config.config_parser import AppConfig
from lastfm_recs_scraper.scraper.lastfm_recs_scraper import (
    LastFMRec,
    LastFMRecsScraper,
    RecContext,
    RecommendationType,
)
from lastfm_recs_scraper.utils.constants import (
    ALBUM_RECS_BASE_URL,
    LOGIN_BUTTON_LOCATOR,
    LOGIN_PASSWORD_FORM_LOCATOR,
    LOGIN_URL,
    LOGIN_USERNAME_FORM_LOCATOR,
    LOGOUT_URL,
    PW_USER_AGENT,
    TRACK_RECS_BASE_URL,
)
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


def test_scraper_enter(lfm_rec_scraper: LastFMRecsScraper) -> None:
    mock_playwright = MagicMock()
    mock_browser = MagicMock()
    with patch.object(PlaywrightContextManager, "start") as mock_sync_playwright_ctx:
        mock_sync_playwright_ctx.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        with patch.object(LastFMRecsScraper, "_user_login") as user_login_mock:
            lfm_rec_scraper.__enter__()
            mock_sync_playwright_ctx.assert_has_calls([call()])
            mock_playwright.assert_has_calls([call.chromium.launch(headless=True)])
            mock_browser.new_page.assert_called_once_with(user_agent=PW_USER_AGENT)
            assert hasattr(lfm_rec_scraper, "_playwright")
            assert hasattr(lfm_rec_scraper, "_browser")
            assert hasattr(lfm_rec_scraper, "_page")
            user_login_mock.assert_called_once()


def test_scraper_exit(lfm_rec_scraper: LastFMRecsScraper) -> None:
    mock_playwright = MagicMock()
    mock_browser = MagicMock()
    mock_page = MagicMock()
    with patch.object(PlaywrightContextManager, "start") as mock_sync_playwright_ctx:
        mock_sync_playwright_ctx.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        with patch.object(LastFMRecsScraper, "_user_login") as user_login_mock:
            with patch.object(LastFMRecsScraper, "_user_logout") as user_logout_mock:
                lfm_rec_scraper.__enter__()
                lfm_rec_scraper.__exit__()
                user_logout_mock.assert_called_once
                lfm_rec_scraper._page.close.assert_called_once()
                lfm_rec_scraper._browser.close.assert_called_once()
                lfm_rec_scraper._playwright.stop.assert_called_once()


def test_context_manager(valid_app_config: AppConfig) -> None:
    with patch.object(LastFMRecsScraper, "__enter__") as enter_mock:
        with patch.object(LastFMRecsScraper, "__exit__") as exit_mock:
            with LastFMRecsScraper(app_config=valid_app_config) as ctx_rec_mgr:
                enter_mock.assert_called_once()
                exit_mock.assert_not_called()
            enter_mock.assert_called_once()
            exit_mock.assert_called_once()


def test_user_login(lfm_rec_scraper: LastFMRecsScraper) -> None:
    lfm_rec_scraper._page = MagicMock()
    username = lfm_rec_scraper._last_fm_username
    password = lfm_rec_scraper._last_fm_password
    with patch("lastfm_recs_scraper.scraper.lastfm_recs_scraper._sleep_random") as mock_sleep_random:
        lfm_rec_scraper._user_login()
        lfm_rec_scraper._page.assert_has_calls(
            [
                call.goto(LOGIN_URL),
                call.locator(LOGIN_USERNAME_FORM_LOCATOR),
                call.locator().fill(username),
                call.locator(LOGIN_PASSWORD_FORM_LOCATOR),
                call.locator().fill(password),
                call.locator(LOGIN_BUTTON_LOCATOR),
                call.locator().click(),
                call.wait_for_url(f"**/user/{username}"),
            ]
        )
        assert (
            lfm_rec_scraper._is_logged_in
        ), f"Expected lfm_rec_scraper._is_logged_in to be True after calling _user_login()."
        mock_sleep_random.assert_called_once()


def test_user_logout(lfm_rec_scraper: LastFMRecsScraper) -> None:
    lfm_rec_scraper._page = MagicMock()
    lfm_rec_scraper._user_logout()
    lfm_rec_scraper._page.assert_has_calls(
        [
            call.goto(LOGOUT_URL),
            call.get_by_role("button", name=re.compile("logout", re.IGNORECASE)),
            call.get_by_role().click(),
            call.wait_for_url("**last.fm/"),
        ]
    )
    assert (
        not lfm_rec_scraper._is_logged_in
    ), f"Expected lfm_rec_scraper._is_logged_in to be False after calling _user_logout()."


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


@pytest.mark.parametrize(
    "rec_type, expected_css_selector",
    [
        (RecommendationType.ALBUM, ".music-recommended-albums-item-name"),
        (RecommendationType.TRACK, ".recommended-tracks-item-name"),
    ],
)
def test_navigate_to_page_and_get_page_source(
    lfm_rec_scraper: LastFMRecsScraper, rec_type: RecommendationType, expected_css_selector: str
) -> None:
    fake_url = "https://google.com"
    lfm_rec_scraper._page = MagicMock()
    with patch("lastfm_recs_scraper.scraper.lastfm_recs_scraper._sleep_random") as mock_sleep_random:
        lfm_rec_scraper._navigate_to_page_and_get_page_source(url=fake_url, rec_type=rec_type)
        lfm_rec_scraper._page.assert_has_calls(
            [
                call.goto(fake_url),
                call.locator(expected_css_selector),
            ]
        )
        mock_sleep_random.assert_called_once()


@pytest.mark.parametrize(
    "rec_type, expected_rec_base_url",
    [
        (RecommendationType.ALBUM, ALBUM_RECS_BASE_URL),
        (RecommendationType.TRACK, TRACK_RECS_BASE_URL),
    ],
)
def test_scrape_recs_list(
    lfm_rec_scraper: LastFMRecsScraper, rec_type: RecommendationType, expected_rec_base_url: str
) -> None:
    with patch.object(LastFMRecsScraper, "_navigate_to_page_and_get_page_source") as mock_navigate_to_page:
        mock_navigate_to_page.return_value = ""
        with patch.object(LastFMRecsScraper, "_extract_recs_from_page_source") as mock_extract_recs:
            mock_extract_recs.return_value = []
            lfm_rec_scraper.scrape_recs_list(recommendation_type=rec_type)
            assert lfm_rec_scraper._scraped_recs[rec_type] is not None
