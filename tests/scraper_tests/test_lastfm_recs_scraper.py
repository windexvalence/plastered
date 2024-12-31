import re
from typing import Any, List
from unittest.mock import MagicMock, call, patch

import pytest
from rebrowser_playwright.sync_api import PlaywrightContextManager

from lastfm_recs_scraper.config.config_parser import AppConfig
from lastfm_recs_scraper.scraper.lastfm_recs_scraper import (
    LastFMRec,
    LastFMRecsScraper,
    RecContext,
    RecommendationType,
    _sleep_random,
)
from lastfm_recs_scraper.utils.constants import (
    ALBUM_RECS_BASE_URL,
    LOGIN_BUTTON_LOCATOR,
    LOGIN_PASSWORD_FORM_LOCATOR,
    LOGIN_URL,
    LOGIN_USERNAME_FORM_LOCATOR,
    LOGOUT_URL,
    PW_USER_AGENT,
    RENDER_WAIT_SEC_MAX,
    RENDER_WAIT_SEC_MIN,
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


@pytest.fixture(scope="session")
def expected_track_recs(expected_album_recs: List[LastFMRec]) -> List[LastFMRec]:
    return [
        LastFMRec(
            lastfm_artist_str="Liquid+Liquid",
            lastfm_entity_str="Cavern",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Yellow+Swans",
            lastfm_entity_str="Foiled",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="William+Basinski",
            lastfm_entity_str="Melancholia+VI",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Blanck+Mass",
            lastfm_entity_str="House+Vs.+House",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Ben+Frost",
            lastfm_entity_str="We+Don%27t+Need+Other+Worlds,+We+Need+Mirrors",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Dr.+Octagon",
            lastfm_entity_str="Technical+Difficulties",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Public+Image+Ltd.",
            lastfm_entity_str="Public+Image+-+Remastered+2011",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Ty+Segall+Band",
            lastfm_entity_str="Wave+Goodbye",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Tim+Hecker+&+Daniel+Lopatin",
            lastfm_entity_str="Ritual+for+Consumption",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Meatbodies",
            lastfm_entity_str="Move",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Aidan+Baker+&+Tim+Hecker",
            lastfm_entity_str="Hymn+to+the+Idea+of+Night",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Wand",
            lastfm_entity_str="Smile",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Pylon",
            lastfm_entity_str="Crazy+-+Remastered",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Fennesz",
            lastfm_entity_str="City+of+Light",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Ultramagnetic+MC%27s",
            lastfm_entity_str="Give+the+Drummer+Some",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Thee+Oh+Sees",
            lastfm_entity_str="Cassius,+Brutus+&+Judas",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Simian+Mobile+Disco",
            lastfm_entity_str="Hustler",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Belong",
            lastfm_entity_str="I+Never+Lose.+Never+Really",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Frankie+and+the+Witch+Fingers",
            lastfm_entity_str="Burn+Me+Down",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LastFMRec(
            lastfm_artist_str="Oneohtrix+Point+Never",
            lastfm_entity_str="Cryo",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
    ]


def test_sleep_random() -> None:
    assert (
        RENDER_WAIT_SEC_MIN > 0
    ), f"Expected constant 'RENDER_WAIT_SEC_MIN' to be greater than 0, but found it set to {RENDER_WAIT_SEC_MIN}"
    assert (
        RENDER_WAIT_SEC_MIN < RENDER_WAIT_SEC_MAX
    ), f"Expected constant 'RENDER_WAIT_SEC_MIN' to be less than constant 'RENDER_WAIT_SEC_MAX', but found {RENDER_WAIT_SEC_MIN} vs. {RENDER_WAIT_SEC_MAX}"
    assert (
        RENDER_WAIT_SEC_MAX < 10
    ), f"Expected constant 'RENDER_WAIT_SEC_MAX' to be less than 10, but found it set to {RENDER_WAIT_SEC_MAX}"
    with patch("lastfm_recs_scraper.scraper.lastfm_recs_scraper.randint") as mock_randint:
        mock_randint.return_value = 5
        with patch("lastfm_recs_scraper.scraper.lastfm_recs_scraper.sleep") as mock_sleep:
            mock_sleep.return_value = None
            _sleep_random()
            mock_randint.assert_called_once_with(RENDER_WAIT_SEC_MIN, RENDER_WAIT_SEC_MAX)
            mock_sleep.assert_called_once_with(mock_randint.return_value)


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


@pytest.mark.parametrize(
    "lfm_rec, expected",
    [
        (
            LastFMRec(
                lastfm_artist_str="Some+Bad+Artist",
                lastfm_entity_str="Some+Dumb+Album",
                recommendation_type=RecommendationType.ALBUM,
                rec_context=RecContext.SIMILAR_ARTIST,
            ),
            "artist=Some+Bad+Artist, album=Some+Dumb+Album, context=similar-artist",
        ),
        (
            LastFMRec(
                lastfm_artist_str="Some+Other+Bad+Artist",
                lastfm_entity_str="Some+Dumb+Track",
                recommendation_type=RecommendationType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            "artist=Some+Other+Bad+Artist, track=Some+Dumb+Track, context=in-library",
        ),
    ],
)
def test_lastfmrec_str(lfm_rec: LastFMRec, expected: str) -> None:
    actual = lfm_rec.__str__()
    assert actual == expected, f"Expected __str__() result to be '{expected}', but got '{actual}'"


@pytest.mark.parametrize(
    "lfm_rec, other, expected",
    [
        (
            LastFMRec(
                lastfm_artist_str="Some+Bad+Artist",
                lastfm_entity_str="Some+Dumb+Album",
                recommendation_type=RecommendationType.ALBUM,
                rec_context=RecContext.SIMILAR_ARTIST,
            ),
            None,
            False,
        ),
        (
            LastFMRec(
                lastfm_artist_str="Some+Bad+Artist",
                lastfm_entity_str="Some+Dumb+Album",
                recommendation_type=RecommendationType.ALBUM,
                rec_context=RecContext.SIMILAR_ARTIST,
            ),
            LastFMRec(
                lastfm_artist_str="Some+Other+Bad+Artist",
                lastfm_entity_str="Some+Dumb+Track",
                recommendation_type=RecommendationType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            False,
        ),
        (
            LastFMRec(
                lastfm_artist_str="Some+Other+Bad+Artist",
                lastfm_entity_str="Some+Dumb+Track",
                recommendation_type=RecommendationType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            LastFMRec(
                lastfm_artist_str="Some+Other+Bad+Artist",
                lastfm_entity_str="Some+Dumb+Track",
                recommendation_type=RecommendationType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            True,
        ),
    ],
)
def test_lastfmrec_eq(lfm_rec: LastFMRec, other: Any, expected: bool) -> None:
    actual = lfm_rec.__eq__(other=other)
    assert actual == expected, f"Expected {lfm_rec}.__eq__(other={other}) result to be '{expected}', but got '{actual}'"


@pytest.mark.parametrize(
    "lfm_rec, expected",
    [
        (
            LastFMRec(
                lastfm_artist_str="Some+Bad+Artist",
                lastfm_entity_str="Some+Dumb+Album",
                recommendation_type=RecommendationType.ALBUM,
                rec_context=RecContext.SIMILAR_ARTIST,
            ),
            False,
        ),
        (
            LastFMRec(
                lastfm_artist_str="Some+Other+Bad+Artist",
                lastfm_entity_str="Some+Dumb+Track",
                recommendation_type=RecommendationType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            True,
        ),
    ],
)
def test_lastfmrec_is_track_rec(lfm_rec: LastFMRec, expected: bool) -> None:
    actual = lfm_rec.is_track_rec()
    assert actual == expected, f"Expected {lfm_rec}.is_track_rec to be {expected}, but got {actual}"


@pytest.mark.parametrize(
    "lfm_rec, expected",
    [
        (
            LastFMRec(
                lastfm_artist_str="Some+Bad+Artist",
                lastfm_entity_str="Some+Dumb+Album",
                recommendation_type=RecommendationType.ALBUM,
                rec_context=RecContext.SIMILAR_ARTIST,
            ),
            "https://www.last.fm/music/Some+Bad+Artist/Some+Dumb+Album",
        ),
        (
            LastFMRec(
                lastfm_artist_str="Some+Other+Bad+Artist",
                lastfm_entity_str="Some+Dumb+Track",
                recommendation_type=RecommendationType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            "https://www.last.fm/music/Some+Other+Bad+Artist/_/Some+Dumb+Track",
        ),
    ],
)
def test_lastfm_entity_url(lfm_rec: LastFMRec, expected: str) -> None:
    actual = lfm_rec.last_fm_entity_url
    assert actual == expected, f"Expected {lfm_rec}.last_fm_entity_url to be '{expected}', but got '{actual}'"


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


@pytest.mark.parametrize("rec_type", [(RecommendationType.ALBUM), (RecommendationType.TRACK)])
def test_extract_recs_from_page_source(
    album_recs_page_one_html: str,
    track_recs_page_one_html: str,
    lfm_rec_scraper: LastFMRecsScraper,
    expected_album_recs: List[LastFMRec],
    expected_track_recs: List[LastFMRec],
    rec_type: RecommendationType,
) -> None:
    if rec_type == RecommendationType.ALBUM:
        mock_page_source = album_recs_page_one_html
        expected_recs = expected_album_recs
    else:
        mock_page_source = track_recs_page_one_html
        expected_recs = expected_track_recs
    actual_recs_list = lfm_rec_scraper._extract_recs_from_page_source(
        page_source=mock_page_source,
        rec_type=rec_type,
    )
    expected_length = len(expected_recs)
    actual_length = len(actual_recs_list)
    assert (
        actual_length == expected_length
    ), f"Expected {expected_length} {rec_type.value} recs, but got {actual_length}."
    for i, actual_rec in enumerate(actual_recs_list):
        expected_rec = expected_recs[i]
        assert (
            actual_rec == expected_rec
        ), f"Expected {i}'th {rec_type.value} rec to be '{str(expected_rec)}' but got '{str(actual_rec)}'"


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
