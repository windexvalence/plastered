import re
from typing import Any, List
from unittest.mock import MagicMock, call, patch

import pytest
from rebrowser_playwright.sync_api import PlaywrightContextManager

from plastered.config.config_parser import AppConfig
from plastered.run_cache.run_cache import CacheType, RunCache
from plastered.scraper.lfm_scraper import (
    LFMRec,
    LFMRecsScraper,
    RecContext,
    RecommendationType,
    _sleep_random,
    cached_lfm_recs_validator,
)
from plastered.utils.constants import (
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
def lfm_rec_scraper(valid_app_config: AppConfig) -> LFMRecsScraper:
    return LFMRecsScraper(app_config=valid_app_config)


# TODO: add a similar expected_track_recs fixture
@pytest.fixture(scope="session")
def expected_album_recs() -> List[LFMRec]:
    return [
        LFMRec(
            lfm_artist_str="Dr.+Octagon",
            lfm_entity_str="Dr.+Octagonecologyst",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Soulwax",
            lfm_entity_str="Much+Against+Everyone%27s+Advice",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
        LFMRec(
            lfm_artist_str="Mission+of+Burma",
            lfm_entity_str="Signals,+Calls+and+Marches",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="The+Fall",
            lfm_entity_str="This+Nation%27s+Saving+Grace",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Bo+Diddley",
            lfm_entity_str="500%25+More+Man",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
        LFMRec(
            lfm_artist_str="MF+DOOM",
            lfm_entity_str="MM...FOOD",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
        LFMRec(
            lfm_artist_str="Black+Moth+Super+Rainbow",
            lfm_entity_str="Dandelion+Gum",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
        LFMRec(
            lfm_artist_str="Magazine",
            lfm_entity_str="Real+Life",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Red+Rider",
            lfm_entity_str="Neruda",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
        LFMRec(
            lfm_artist_str="Pylon",
            lfm_entity_str="Chomp+(Remastered)",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Thee+Oh+Sees",
            lfm_entity_str="Floating+Coffin",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Minutemen",
            lfm_entity_str="Double+Nickels+on+the+Dime",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Ty+Segall+Band",
            lfm_entity_str="Slaughterhouse",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Television",
            lfm_entity_str="Marquee+Moon",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Factory+Floor",
            lfm_entity_str="Lying+%2F+A+Wooden+Box",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
        LFMRec(
            lfm_artist_str="Donovan",
            lfm_entity_str="Sunshine+Superman",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
        LFMRec(
            lfm_artist_str="The+Pop+Group",
            lfm_entity_str="Y",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="FrankJavCee",
            lfm_entity_str="FrankJavCee+Collection,+Vol.+1,+Pt.+II",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
        LFMRec(
            lfm_artist_str="Public+Image+Ltd.",
            lfm_entity_str="Metal+Box",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Wire",
            lfm_entity_str="Chairs+Missing",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.IN_LIBRARY,
        ),
    ]


@pytest.fixture(scope="session")
def expected_track_recs(expected_album_recs: List[LFMRec]) -> List[LFMRec]:
    return [
        LFMRec(
            lfm_artist_str="Liquid+Liquid",
            lfm_entity_str="Cavern",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Yellow+Swans",
            lfm_entity_str="Foiled",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="William+Basinski",
            lfm_entity_str="Melancholia+VI",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Blanck+Mass",
            lfm_entity_str="House+Vs.+House",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Ben+Frost",
            lfm_entity_str="We+Don%27t+Need+Other+Worlds,+We+Need+Mirrors",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Dr.+Octagon",
            lfm_entity_str="Technical+Difficulties",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Public+Image+Ltd.",
            lfm_entity_str="Public+Image+-+Remastered+2011",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Ty+Segall+Band",
            lfm_entity_str="Wave+Goodbye",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Tim+Hecker+&+Daniel+Lopatin",
            lfm_entity_str="Ritual+for+Consumption",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Meatbodies",
            lfm_entity_str="Move",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Aidan+Baker+&+Tim+Hecker",
            lfm_entity_str="Hymn+to+the+Idea+of+Night",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Wand",
            lfm_entity_str="Smile",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Pylon",
            lfm_entity_str="Crazy+-+Remastered",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Fennesz",
            lfm_entity_str="City+of+Light",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Ultramagnetic+MC%27s",
            lfm_entity_str="Give+the+Drummer+Some",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Thee+Oh+Sees",
            lfm_entity_str="Cassius,+Brutus+&+Judas",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Simian+Mobile+Disco",
            lfm_entity_str="Hustler",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Belong",
            lfm_entity_str="I+Never+Lose.+Never+Really",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Frankie+and+the+Witch+Fingers",
            lfm_entity_str="Burn+Me+Down",
            recommendation_type=RecommendationType.TRACK,
            rec_context=RecContext.SIMILAR_ARTIST,
        ),
        LFMRec(
            lfm_artist_str="Oneohtrix+Point+Never",
            lfm_entity_str="Cryo",
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
    with patch("plastered.scraper.lfm_scraper.randint") as mock_randint:
        mock_randint.return_value = 5
        with patch("plastered.scraper.lfm_scraper.sleep") as mock_sleep:
            mock_sleep.return_value = None
            _sleep_random()
            mock_randint.assert_called_once_with(RENDER_WAIT_SEC_MIN, RENDER_WAIT_SEC_MAX)
            mock_sleep.assert_called_once_with(mock_randint.return_value)


@pytest.mark.parametrize(
    "cached_data, expected",
    [
        ({}, False),
        ([None], False),
        (["Not a LFMRec"], False),
        (
            tuple(
                [
                    LFMRec(
                        lfm_artist_str="A",
                        lfm_entity_str="B",
                        recommendation_type=RecommendationType.ALBUM,
                        rec_context=RecContext.IN_LIBRARY,
                    )
                ]
            ),
            False,
        ),
        ([], True),
        (
            [
                LFMRec(
                    lfm_artist_str="Factory+Floor",
                    lfm_entity_str="Lying+%2F+A+Wooden+Box",
                    recommendation_type=RecommendationType.ALBUM,
                    rec_context=RecContext.IN_LIBRARY,
                ),
            ],
            True,
        ),
        (
            [
                LFMRec(
                    lfm_artist_str="Factory+Floor",
                    lfm_entity_str="Lying+%2F+A+Wooden+Box",
                    recommendation_type=RecommendationType.ALBUM,
                    rec_context=RecContext.IN_LIBRARY,
                ),
                LFMRec(
                    lfm_artist_str="A",
                    lfm_entity_str="B",
                    recommendation_type=RecommendationType.ALBUM,
                    rec_context=RecContext.IN_LIBRARY,
                ),
            ],
            True,
        ),
    ],
)
def test_cached_album_recs_validator(
    cached_data: Any,
    expected: bool,
) -> None:
    actual = cached_lfm_recs_validator(cached_data=cached_data)
    assert actual == expected, f"Expected {expected}, but got {actual}"


def test_scraper_init(lfm_rec_scraper: LFMRecsScraper, valid_app_config: AppConfig) -> None:
    with patch.object(LFMRecsScraper, "__enter__") as enter_method_mock:
        enter_method_mock.assert_not_called()
    with patch.object(LFMRecsScraper, "__exit__") as exit_method_mock:
        exit_method_mock.assert_not_called()
    expected_username = valid_app_config.get_cli_option("lfm_username")
    actual_username = lfm_rec_scraper._lfm_username
    assert (
        actual_username == expected_username
    ), f"Unexpected username in LFMRecsScraper instance: '{actual_username}'. Expected: '{expected_username}'"
    expected_password = valid_app_config.get_cli_option("lfm_password")
    actual_password = lfm_rec_scraper._lfm_password
    assert (
        actual_password == expected_password
    ), f"Unexpected password in LFMRecsScraper instance: '{actual_password}'. Expected: '{expected_password}'"
    expected_is_logged_in = False
    actual_is_logged_in = lfm_rec_scraper._is_logged_in
    assert (
        actual_is_logged_in == expected_is_logged_in
    ), f"Expected LFMRecsScraper instance's _is_logged_in field to be False up __init__ call, but was {actual_is_logged_in}"


@pytest.mark.parametrize(
    "lfm_rec, expected",
    [
        (
            LFMRec(
                lfm_artist_str="Some+Bad+Artist",
                lfm_entity_str="Some+Dumb+Album",
                recommendation_type=RecommendationType.ALBUM,
                rec_context=RecContext.SIMILAR_ARTIST,
            ),
            "artist=Some+Bad+Artist, album=Some+Dumb+Album, context=similar-artist",
        ),
        (
            LFMRec(
                lfm_artist_str="Some+Other+Bad+Artist",
                lfm_entity_str="Some+Dumb+Track",
                recommendation_type=RecommendationType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            "artist=Some+Other+Bad+Artist, track=Some+Dumb+Track, context=in-library",
        ),
    ],
)
def test_lfmrec_str(lfm_rec: LFMRec, expected: str) -> None:
    actual = lfm_rec.__str__()
    assert actual == expected, f"Expected __str__() result to be '{expected}', but got '{actual}'"


@pytest.mark.parametrize(
    "lfm_str, expected",
    [
        ("", ""),
        ("Singleword", "Singleword"),
        ("lowercase", "lowercase"),
        ("Aphex+Twin", "Aphex Twin"),
        ("Aphex Twin", "Aphex Twin"),
        ("Double+Nickels+On+The+Dime", "Double Nickels On The Dime"),
        ("Dr.+Octagonecologyst", "Dr. Octagonecologyst"),
        ("Much+Against+Everyone%27s+Advice", "Much Against Everyone's Advice"),
        ("Signals,+Calls+and+Marches", "Signals, Calls and Marches"),
        ("This+Nation%27s+Saving+Grace", "This Nation's Saving Grace"),
        ("500%25+More+Man", "500% More Man"),
        ("MM...FOOD", "MM...FOOD"),
        ("Chomp+(Remastered)", "Chomp (Remastered)"),
        ("Lying+%2f+a+Wooden+Box", "Lying / a Wooden Box"),
        ("Y", "Y"),
        ("Frankjavcee+Collection,+Vol.+1,+pt.+II", "Frankjavcee Collection, Vol. 1, pt. II"),
        ("Public+Image+LTD.", "Public Image LTD."),
    ],
)
def test_get_human_readable_artist_str(lfm_str: str, expected: str) -> None:
    test_lfm_rec = LFMRec(
        lfm_artist_str=lfm_str,
        lfm_entity_str="Fake+Release",
        recommendation_type=RecommendationType.ALBUM,
        rec_context=RecContext.SIMILAR_ARTIST,
    )
    actual = test_lfm_rec.get_human_readable_artist_str()
    assert (
        actual == expected
    ), f"Expected LFMRec.get_human_readable_artist_str() to return '{expected}', but got '{actual}'"


@pytest.mark.parametrize(
    "lfm_rec, other, expected",
    [
        (
            LFMRec(
                lfm_artist_str="Some+Bad+Artist",
                lfm_entity_str="Some+Dumb+Album",
                recommendation_type=RecommendationType.ALBUM,
                rec_context=RecContext.SIMILAR_ARTIST,
            ),
            None,
            False,
        ),
        (
            LFMRec(
                lfm_artist_str="Some+Bad+Artist",
                lfm_entity_str="Some+Dumb+Album",
                recommendation_type=RecommendationType.ALBUM,
                rec_context=RecContext.SIMILAR_ARTIST,
            ),
            LFMRec(
                lfm_artist_str="Some+Other+Bad+Artist",
                lfm_entity_str="Some+Dumb+Track",
                recommendation_type=RecommendationType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            False,
        ),
        (
            LFMRec(
                lfm_artist_str="Some+Other+Bad+Artist",
                lfm_entity_str="Some+Dumb+Track",
                recommendation_type=RecommendationType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            LFMRec(
                lfm_artist_str="Some+Other+Bad+Artist",
                lfm_entity_str="Some+Dumb+Track",
                recommendation_type=RecommendationType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            True,
        ),
    ],
)
def test_lfmrec_eq(lfm_rec: LFMRec, other: Any, expected: bool) -> None:
    actual = lfm_rec.__eq__(other=other)
    assert actual == expected, f"Expected {lfm_rec}.__eq__(other={other}) result to be '{expected}', but got '{actual}'"


@pytest.mark.parametrize(
    "lfm_rec, expected",
    [
        (
            LFMRec(
                lfm_artist_str="Some+Bad+Artist",
                lfm_entity_str="Some+Dumb+Album",
                recommendation_type=RecommendationType.ALBUM,
                rec_context=RecContext.SIMILAR_ARTIST,
            ),
            False,
        ),
        (
            LFMRec(
                lfm_artist_str="Some+Other+Bad+Artist",
                lfm_entity_str="Some+Dumb+Track",
                recommendation_type=RecommendationType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            True,
        ),
    ],
)
def test_lfmrec_is_track_rec(lfm_rec: LFMRec, expected: bool) -> None:
    actual = lfm_rec.is_track_rec()
    assert actual == expected, f"Expected {lfm_rec}.is_track_rec to be {expected}, but got {actual}"


@pytest.mark.parametrize(
    "lfm_rec, expected",
    [
        (
            LFMRec(
                lfm_artist_str="Some+Bad+Artist",
                lfm_entity_str="Some+Dumb+Album",
                recommendation_type=RecommendationType.ALBUM,
                rec_context=RecContext.SIMILAR_ARTIST,
            ),
            "https://www.last.fm/music/Some+Bad+Artist/Some+Dumb+Album",
        ),
        (
            LFMRec(
                lfm_artist_str="Some+Other+Bad+Artist",
                lfm_entity_str="Some+Dumb+Track",
                recommendation_type=RecommendationType.TRACK,
                rec_context=RecContext.IN_LIBRARY,
            ),
            "https://www.last.fm/music/Some+Other+Bad+Artist/_/Some+Dumb+Track",
        ),
    ],
)
def test_lfm_entity_url(lfm_rec: LFMRec, expected: str) -> None:
    actual = lfm_rec.lfm_entity_url
    assert actual == expected, f"Expected {lfm_rec}.lfm_entity_url to be '{expected}', but got '{actual}'"


def test_scraper_enter_no_cache(lfm_rec_scraper: LFMRecsScraper) -> None:
    mock_playwright = MagicMock()
    mock_browser = MagicMock()
    with patch.object(PlaywrightContextManager, "start") as mock_sync_playwright_ctx:
        mock_sync_playwright_ctx.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        with patch.object(LFMRecsScraper, "_user_login") as user_login_mock:
            lfm_rec_scraper.__enter__()
            mock_sync_playwright_ctx.assert_has_calls([call()])
            mock_playwright.assert_has_calls([call.chromium.launch(headless=True)])
            mock_browser.new_page.assert_called_once_with(user_agent=PW_USER_AGENT)
            assert lfm_rec_scraper._playwright is not None
            assert lfm_rec_scraper._browser is not None
            assert lfm_rec_scraper._page is not None
            user_login_mock.assert_called_once()


def test_scraper_enter_with_cache(lfm_rec_scraper: LFMRecsScraper) -> None:
    mock_playwright = MagicMock()
    mock_browser = MagicMock()
    with patch.object(PlaywrightContextManager, "start") as mock_sync_playwright_ctx:
        mock_sync_playwright_ctx.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        with patch.object(RunCache, "load_data_if_valid") as mock_run_cache_load:
            mock_run_cache_load.return_value = True
            with patch.object(LFMRecsScraper, "_user_login") as user_login_mock:
                lfm_rec_scraper.__enter__()
                mock_sync_playwright_ctx.assert_not_called()
                mock_playwright.assert_not_called()
                mock_browser.new_page.assert_not_called()
                assert lfm_rec_scraper._playwright is None
                assert lfm_rec_scraper._browser is None
                assert lfm_rec_scraper._page is None
                user_login_mock.assert_not_called()


def test_scraper_exit_no_cache(lfm_rec_scraper: LFMRecsScraper) -> None:
    mock_playwright = MagicMock()
    mock_browser = MagicMock()
    mock_page = MagicMock()
    with patch.object(PlaywrightContextManager, "start") as mock_sync_playwright_ctx:
        mock_sync_playwright_ctx.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        with patch.object(LFMRecsScraper, "_user_login") as user_login_mock:
            with patch.object(LFMRecsScraper, "_user_logout") as user_logout_mock:
                lfm_rec_scraper.__enter__()
                lfm_rec_scraper._is_logged_in = True
                lfm_rec_scraper.__exit__(exc_type=None, exc_val=None, exc_tb=None)
                user_logout_mock.assert_called_once()
                lfm_rec_scraper._page.close.assert_called_once()
                mock_browser.close.assert_called_once()
                mock_playwright.stop.assert_called_once()


def test_scraper_exit_with_cache(lfm_rec_scraper: LFMRecsScraper) -> None:
    mock_playwright = MagicMock()
    mock_browser = MagicMock()
    mock_page = MagicMock()
    with patch.object(PlaywrightContextManager, "start") as mock_sync_playwright_ctx:
        mock_sync_playwright_ctx.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_run_cache = MagicMock()
        with patch("plastered.scraper.lfm_scraper.RunCache") as mock_run_cache_constructor:
            mock_run_cache_constructor.return_value = mock_run_cache
            mock_run_cache.load_data_if_valid.return_value = True
            mock_run_cache.close.return_value = None
            with patch.object(LFMRecsScraper, "_user_login") as user_login_mock:
                with patch.object(LFMRecsScraper, "_user_logout") as user_logout_mock:
                    lfm_rec_scraper._run_cache = mock_run_cache
                    lfm_rec_scraper.__enter__()
                    lfm_rec_scraper.__exit__(exc_type=None, exc_val=None, exc_tb=None)
                    mock_run_cache.close.assert_called_once()
                    user_logout_mock.assert_not_called()
                    mock_browser.close.assert_not_called()
                    mock_playwright.stop.assert_not_called()
                    assert lfm_rec_scraper._playwright is None
                    assert lfm_rec_scraper._browser is None
                    assert lfm_rec_scraper._page is None


def test_context_manager(valid_app_config: AppConfig) -> None:
    with patch.object(LFMRecsScraper, "__enter__") as enter_mock:
        with patch.object(LFMRecsScraper, "__exit__") as exit_mock:
            with LFMRecsScraper(app_config=valid_app_config) as ctx_rec_mgr:
                enter_mock.assert_called_once()
                exit_mock.assert_not_called()
            enter_mock.assert_called_once()
            exit_mock.assert_called_once()


def test_user_login(lfm_rec_scraper: LFMRecsScraper) -> None:
    lfm_rec_scraper._page = MagicMock()
    username = lfm_rec_scraper._lfm_username
    password = lfm_rec_scraper._lfm_password
    with patch("plastered.scraper.lfm_scraper._sleep_random") as mock_sleep_random:
        lfm_rec_scraper._user_login()
        lfm_rec_scraper._page.assert_has_calls(
            [
                call.goto(LOGIN_URL, wait_until="domcontentloaded"),
                call.locator(LOGIN_USERNAME_FORM_LOCATOR),
                call.locator().fill(username),
                call.locator(LOGIN_PASSWORD_FORM_LOCATOR),
                call.locator().fill(password),
                call.locator(LOGIN_BUTTON_LOCATOR),
                call.locator().click(),
            ]
        )
        assert (
            lfm_rec_scraper._is_logged_in
        ), f"Expected lfm_rec_scraper._is_logged_in to be True after calling _user_login()."
        mock_sleep_random.assert_called_once()


def test_user_logout(lfm_rec_scraper: LFMRecsScraper) -> None:
    lfm_rec_scraper._page = MagicMock()
    lfm_rec_scraper._user_logout()
    lfm_rec_scraper._page.assert_has_calls(
        [
            call.goto(LOGOUT_URL, wait_until="domcontentloaded"),
            call.get_by_role("button", name=re.compile("logout", re.IGNORECASE)),
            call.get_by_role().locator("visible=true"),
            call.get_by_role().locator().first.click(),
        ]
    )
    assert (
        not lfm_rec_scraper._is_logged_in
    ), f"Expected lfm_rec_scraper._is_logged_in to be False after calling _user_logout()."


@pytest.mark.parametrize("rec_type", [(RecommendationType.ALBUM), (RecommendationType.TRACK)])
def test_extract_recs_from_page_source(
    album_recs_page_one_html: str,
    track_recs_page_one_html: str,
    lfm_rec_scraper: LFMRecsScraper,
    expected_album_recs: List[LFMRec],
    expected_track_recs: List[LFMRec],
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
    lfm_rec_scraper: LFMRecsScraper, rec_type: RecommendationType, expected_css_selector: str
) -> None:
    fake_url = "https://google.com"
    lfm_rec_scraper._page = MagicMock()
    with patch("plastered.scraper.lfm_scraper._sleep_random") as mock_sleep_random:
        lfm_rec_scraper._navigate_to_page_and_get_page_source(url=fake_url, rec_type=rec_type)
        lfm_rec_scraper._page.assert_has_calls(
            [
                call.goto(fake_url, wait_until="domcontentloaded"),
                call.locator(expected_css_selector),
                call.content(),
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
    lfm_rec_scraper: LFMRecsScraper, rec_type: RecommendationType, expected_rec_base_url: str
) -> None:
    with patch.object(LFMRecsScraper, "_navigate_to_page_and_get_page_source") as mock_navigate_to_page:
        mock_navigate_to_page.return_value = ""
        with patch.object(LFMRecsScraper, "_extract_recs_from_page_source") as mock_extract_recs:
            mock_extract_recs.return_value = []
            lfm_rec_scraper._scrape_recs_list(rec_type=rec_type)
            mock_navigate_to_page.assert_called()
            mock_extract_recs.assert_called()


def test_scrape_recs_list_cache_hit(lfm_rec_scraper: LFMRecsScraper) -> None:
    lfm_rec_scraper._loaded_from_run_cache = {
        RecommendationType.ALBUM: [LFMRec("A", "B", RecommendationType.ALBUM, RecContext.SIMILAR_ARTIST)],
        RecommendationType.TRACK: [LFMRec("A+Artist", "A+Song", RecommendationType.TRACK, RecContext.IN_LIBRARY)],
    }
    with patch.object(LFMRecsScraper, "_navigate_to_page_and_get_page_source") as mock_navigate_to_page:
        mock_navigate_to_page.return_value = ""
        with patch.object(LFMRecsScraper, "_extract_recs_from_page_source") as mock_extract_recs:
            mock_extract_recs.return_value = []
            lfm_rec_scraper._scrape_recs_list(RecommendationType.ALBUM)
            mock_navigate_to_page.assert_not_called()
            mock_extract_recs.assert_not_called()
