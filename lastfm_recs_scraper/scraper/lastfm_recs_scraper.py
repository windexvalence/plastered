import os
import re
import sys
from enum import Enum
from random import randint
from time import sleep
from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from rebrowser_playwright.sync_api import sync_playwright

from lastfm_recs_scraper.config.config_parser import AppConfig
from lastfm_recs_scraper.utils.constants import (
    ALBUM_REC_CONTEXT_BS4_CSS_SELECTOR,
    ALBUM_REC_LIST_ELEMENT_BS4_CSS_SELECTOR,
    ALBUM_REC_LIST_ELEMENT_CSS_SELECTOR,
    ALBUM_RECS_BASE_URL,
    LOGIN_BUTTON_LOCATOR,
    LOGIN_PASSWORD_FORM_LOCATOR,
    LOGIN_URL,
    LOGIN_USERNAME_FORM_LOCATOR,
    LOGOUT_URL,
    PW_USER_AGENT,
    TRACK_REC_CONTEXT_CSS_SELECTOR,
    TRACK_REC_LIST_ELEMENT_BS4_CSS_SELECTOR,
    TRACK_REC_LIST_ELEMENT_CSS_SELECTOR,
    TRACK_RECS_BASE_URL,
)
from lastfm_recs_scraper.utils.logging_utils import get_custom_logger

_LOGGER = get_custom_logger(__name__)

_RENDER_WAIT_SEC_MIN = 3
_RENDER_WAIT_SEC_MAX = 7

_ARTIST_ALBUM_REGEX_PATTERN = re.compile(r"^\/music\/([^\/]+)\/(.+)$")
_ARTIST_TRACK_REGEX_PATTERN = re.compile(r"^\/music\/([^\/]+)\/_\/(.+)$")


class RecommendationType(Enum):
    ALBUM = "album"
    TRACK = "track"


class RecContext(Enum):
    IN_LIBRARY = "in-library"
    SIMILAR_ARTIST = "similar-artist"


class LastFMRec(object):
    def __init__(
        self,
        lastfm_artist_str: str,
        lastfm_entity_str: str,
        recommendation_type: RecommendationType,
        rec_context: RecContext,
    ):
        self._lastfm_artist_str = lastfm_artist_str
        self._lastfm_entity_str = lastfm_entity_str
        self._recommendation_type = recommendation_type
        self._rec_context = rec_context

    def __str__(self) -> str:
        return f"artist={self._lastfm_artist_str}, {self._recommendation_type.value}={self._lastfm_entity_str}, context={self._rec_context}"

    def __eq__(self, other) -> bool:
        if not isinstance(other, LastFMRec):
            return False
        return (
            self.artist_str == other.artist_str
            and self.entity_str == other.entity_str
            and self.is_album_rec() == other.is_album_rec()
            and self.rec_context.value == other.rec_context.value
        )

    def is_album_rec(self) -> bool:
        return self._recommendation_type == RecommendationType.ALBUM

    def is_track_rec(self) -> bool:
        return self._recommendation_type == RecommendationType.TRACK

    @property
    def artist_str(self) -> str:
        return self._lastfm_artist_str

    @property
    def entity_str(self) -> str:
        return self._lastfm_entity_str

    @property
    def rec_context(self) -> RecContext:
        return self._rec_context

    @property
    def last_fm_entity_url(self) -> str:
        if self._recommendation_type == RecommendationType.ALBUM:
            return f"https://www.last.fm/music/{self._lastfm_artist_str}/{self._lastfm_entity_str}"
        return f"https://www.last.fm/music/{self._lastfm_artist_str}/_/{self._lastfm_entity_str}"


def _sleep_random() -> None:  # pragma: no cover
    """
    Very dumb utility function to sleep a bounded random number of seconds between selenium client interactions with the lastfm website to try avoid bot detection.
    """
    sleep_seconds = randint(_RENDER_WAIT_SEC_MIN, _RENDER_WAIT_SEC_MAX)
    _LOGGER.debug(f"Sleeping for {sleep_seconds} before continuing ...")
    sleep(sleep_seconds)


# TODO: surface the constructor args as AppConfig / yaml config fields
class LastFMRecsScraper(object):
    def __init__(self, app_config: AppConfig):
        self._max_rec_pages_to_scrape = app_config.get_cli_option("scraper_max_rec_pages_to_scrape")
        self._allow_library_items = app_config.get_cli_option("scraper_allow_library_items")
        # TODO: figure out how to have container dynamically find this from the port arg in docker-compose
        self._last_fm_username = app_config.get_cli_option("last_fm_username")
        self._last_fm_password = app_config.get_cli_option("last_fm_password")
        self._login_success_url = f"https://www.last.fm/user/{self._last_fm_username}"
        self._is_logged_in = False
        self._scraped_recs: Dict[RecommendationType, Optional[List[LastFMRec]]] = {
            RecommendationType.ALBUM: None,
            RecommendationType.TRACK: None,
        }

    def __enter__(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._page = self._browser.new_page(user_agent=PW_USER_AGENT)
        self._user_login()

    def __exit__(self):
        self._user_logout()
        self._page.close()
        self._browser.close()
        self._playwright.stop()

    def _user_login(self) -> None:
        _LOGGER.debug(f"Attempting login ...")
        self._page.goto(LOGIN_URL)
        self._page.locator(LOGIN_USERNAME_FORM_LOCATOR).fill(self._last_fm_username)
        self._page.locator(LOGIN_PASSWORD_FORM_LOCATOR).fill(self._last_fm_password)
        self._page.locator(LOGIN_BUTTON_LOCATOR).click()
        self._page.wait_for_url(f"**/user/{self._last_fm_username}")
        self._is_logged_in = True
        _sleep_random()
        _LOGGER.debug(f"Current driver page URL: {self._page.url}")

    def _user_logout(self) -> None:
        _LOGGER.debug(f"Logging out from last.fm account ...")
        self._page.goto(LOGOUT_URL)
        self._page.get_by_role("button", name=re.compile("logout", re.IGNORECASE)).click()
        self._page.wait_for_url("**last.fm/")
        self._is_logged_in = False

    def _navigate_to_page_and_get_page_source(self, url: str, rec_type: RecommendationType) -> str:
        _LOGGER.info(f"Rendering {url} page source ...")
        self._page.goto(url)
        wait_css_selector = (
            ALBUM_REC_LIST_ELEMENT_CSS_SELECTOR
            if rec_type == RecommendationType.ALBUM
            else TRACK_REC_LIST_ELEMENT_CSS_SELECTOR
        )
        recs_page_locator = self._page.locator(wait_css_selector)
        _sleep_random()
        return self._page.content()

    def _extract_recs_from_page_source(self, page_source: str, rec_type: RecommendationType) -> List[LastFMRec]:
        soup = BeautifulSoup(page_source, "html.parser")
        if rec_type == RecommendationType.ALBUM:
            rec_class_name = ALBUM_REC_LIST_ELEMENT_BS4_CSS_SELECTOR
            entity_rec_context_class_name = ALBUM_REC_CONTEXT_BS4_CSS_SELECTOR
            recommendation_regex_pattern = _ARTIST_ALBUM_REGEX_PATTERN
        else:
            rec_class_name = TRACK_REC_LIST_ELEMENT_BS4_CSS_SELECTOR
            entity_rec_context_class_name = TRACK_REC_CONTEXT_CSS_SELECTOR
            recommendation_regex_pattern = _ARTIST_TRACK_REGEX_PATTERN

        rec_hrefs = [li.get("href") for li in soup.select(rec_class_name)]
        entity_rec_contexts = [elem.text.strip() for elem in soup.select(entity_rec_context_class_name)]
        page_recs: List[LastFMRec] = []
        for i, href_value in enumerate(rec_hrefs):
            regex_match = re.match(recommendation_regex_pattern, href_value)
            artist, entity = regex_match.groups()
            entity_rec_context = (
                RecContext.IN_LIBRARY
                if entity_rec_contexts[i].endswith("in your library")
                else RecContext.SIMILAR_ARTIST
            )
            _LOGGER.info(f"artist: {artist}")
            _LOGGER.info(f"{rec_type.value}: {entity}")
            page_recs.append(
                LastFMRec(
                    lastfm_artist_str=artist,
                    lastfm_entity_str=entity,
                    recommendation_type=rec_type,
                    rec_context=entity_rec_context,
                )
            )
        return page_recs

    def scrape_recs_list(self, recommendation_type: RecommendationType) -> List[LastFMRec]:
        _LOGGER.info(f"Scraping '{recommendation_type.value}' recommendations from LastFM ...")
        recs: List[LastFMRec] = []
        recs_base_url = ALBUM_RECS_BASE_URL if recommendation_type == RecommendationType.ALBUM else TRACK_RECS_BASE_URL
        for page_number in range(1, self._max_rec_pages_to_scrape + 1):
            recs_page_url = f"{recs_base_url}?page={page_number}"
            recs_page_source = self._navigate_to_page_and_get_page_source(
                url=recs_page_url, rec_type=recommendation_type
            )
            recs.extend(self._extract_recs_from_page_source(page_source=recs_page_source))

        self._scraped_recs[recommendation_type] = recs
        return recs
