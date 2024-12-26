from enum import Enum
import os
from random import randint
import re
import sys
from time import sleep
from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config.config_parser import AppConfig
from utils.logging_utils import get_custom_logger


_LOGGER = get_custom_logger(__name__)

_LOGIN_URL = "https://www.last.fm/login"
_LOGIN_USERNAME_INPUT_CSS_SELECTOR = "input[name='username_or_email'][type='text']"
_LOGIN_PASSWORD_INPUT_CSS_SELECTOR = "input[name='password'][type='password']"
_LOGIN_BUTTON_CSS_SELECTOR = ".button.btn-primary[type='submit'][name='submit']"

_LOGOUT_URL = "https://www.last.fm/logout"
_LOGOUT_BUTTON_CSS_SELECTOR = ".button.btn-primary[type='submit']"
_LOGOUT_SUCCESS_URL = "https://www.last.fm/"

_FORCED_LOGIN_URLS = {"https://www.last.fm/login?next=/music/%2Brecommended/albums", "https://www.last.fm/login?next=/music/%2Brecommended/tracks"}
_ALBUM_RECS_BASE_URL = "https://www.last.fm/music/+recommended/albums"
_ALBUM_REC_LIST_ELEMENT_CSS_SELECTOR = ".music-recommended-albums-item-name a.link-block-target"
_ALBUM_REC_CONTEXT_CSS_SELECTOR = "p.music-recommended-albums-album-context"

_TRACK_RECS_BASE_URL = "https://www.last.fm/music/+recommended/tracks"
_TRACK_REC_LIST_ELEMENT_CSS_SELECTOR = ".recommended-tracks-item-name a.link-block-target"
_TRACK_REC_CONTEXT_CSS_SELECTOR = "p.recommended-tracks-item-aux-text.recommended-tracks-item-context"

_CHROMEDRIVER_EXECUTABLE_PATH = "/usr/bin/chromedriver"
sys.path.append(_CHROMEDRIVER_EXECUTABLE_PATH)
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
    def __init__(self, lastfm_artist_str: str, lastfm_entity_str: str, recommendation_type: RecommendationType, rec_context: RecContext):
        self._lastfm_artist_str = lastfm_artist_str
        self._lastfm_entity_str = lastfm_entity_str
        self._recommendation_type = recommendation_type
        self._rec_context = rec_context
    
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


def _sleep_random() -> None:
    """
    Very dumb utility function to sleep a bounded random number of seconds between selenium client interactions with the lastfm website to try avoid bot detection.
    """
    sleep_seconds = randint(_RENDER_WAIT_SEC_MIN, _RENDER_WAIT_SEC_MAX)
    _LOGGER.debug(f"Sleeping for {sleep_seconds} before continuing ...")
    sleep(sleep_seconds)


# TODO: surface the constructor args as AppConfig / yaml config fields
class LastFMRecsScraper(object):
    def __init__(self, app_config: AppConfig):
        self._page_load_timeout_seconds = app_config.get_cli_option("scraper_page_load_timeout_seconds")
        self._max_rec_pages_to_scrape = app_config.get_cli_option("scraper_max_rec_pages_to_scrape")
        self._allow_library_items = app_config.get_cli_option("scraper_allow_library_items")
        self._scraper_service_port = app_config.get_cli_option("scraper_service_port")
        self._last_fm_username = app_config.get_cli_option("last_fm_username")
        self._last_fm_password = app_config.get_cli_option("last_fm_password")
        self._login_success_url = f"https://www.last.fm/user/{self._last_fm_username}"
        self._is_logged_in = False
        self._scraped_recs: Dict[RecommendationType, Optional[List[LastFMRec]]] = {
            RecommendationType.ALBUM: None,
            RecommendationType.TRACK: None,
        }

        self._chrome_driver_options = webdriver.ChromeOptions()
        self._chrome_driver_options.add_argument("--no-sandbox")
        self._chrome_driver_options.add_argument("--headless")
        self._chrome_driver_options.add_argument("--disable-gpu")
        self._chrome_driver_options.add_argument("--disable-dev-shm-usage")
        self._chrome_driver_options.add_argument("--user-data-dir=/tmp/chrome")
    
    def __enter__(self):
        self._service = webdriver.ChromeService(executable_path=_CHROMEDRIVER_EXECUTABLE_PATH, port=self._scraper_service_port)
        self._driver = webdriver.Chrome(options=self._chrome_driver_options, service=self._service)
        # https://selenium-python.readthedocs.io/waits.html#implicit-waits
        self._wait = WebDriverWait(self._driver, self._page_load_timeout_seconds)
        self._user_login()
    
    def __exit__(self):
        self._user_logout()
        self._driver.quit()

    def _user_login(self) -> None:
        _LOGGER.debug(f"Attempting login ...")
        self._driver.get(_LOGIN_URL)
        login_user_form, login_pass_form, login_button = self._wait.until(
            EC.all_of(
                EC.visibility_of_element_located((By.CSS_SELECTOR, _LOGIN_USERNAME_INPUT_CSS_SELECTOR)),
                EC.visibility_of_element_located((By.CSS_SELECTOR, _LOGIN_PASSWORD_INPUT_CSS_SELECTOR)),
                EC.visibility_of_element_located((By.CSS_SELECTOR, _LOGIN_BUTTON_CSS_SELECTOR)),
            )
        )
        login_user_form.send_keys(self._last_fm_username)
        login_pass_form.send_keys(self._last_fm_password)
        login_button.click()
        self._wait.until(EC.url_changes(url=self._login_success_url))
        self._is_logged_in = True
        _sleep_random()
        _LOGGER.debug(f"Current driver page URL: {self._driver.current_url}")
    
    def _user_logout(self) -> None:
        _LOGGER.debug(f"Logging out from last.fm account ...")
        self._driver.get(_LOGOUT_URL)
        logout_button = self._wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, _LOGOUT_BUTTON_CSS_SELECTOR))
        )
        logout_button.click()
        self._wait.until(EC.url_changes(url=_LOGOUT_SUCCESS_URL))
        self._is_logged_in = False

    def _navigate_to_page_and_get_page_source(self, url: str, rec_type: RecommendationType) -> str:
        _LOGGER.info(f"Rendering {url} page source ...")
        self._driver.get(url)
        wait_css_selector = _ALBUM_REC_LIST_ELEMENT_CSS_SELECTOR if rec_type == RecommendationType.ALBUM else _TRACK_REC_LIST_ELEMENT_CSS_SELECTOR
        self._wait.unitl(
            EC.visibility_of_all_elements_located((By.CSS_SELECTOR, wait_css_selector))
        )
        _sleep_random()
        return self._driver.page_source

    def _extract_recs_from_page_source(self, page_source: str, rec_type: RecommendationType) -> List[LastFMRec]:
        soup = BeautifulSoup(page_source, "html.parser")
        if rec_type == RecommendationType.ALBUM:
            rec_class_name = _ALBUM_REC_LIST_ELEMENT_CSS_SELECTOR
            entity_rec_context_class_name = _ALBUM_REC_CONTEXT_CSS_SELECTOR
            recommendation_regex_pattern = _ARTIST_ALBUM_REGEX_PATTERN
        else:
            rec_class_name = _TRACK_REC_LIST_ELEMENT_CSS_SELECTOR
            entity_rec_context_class_name = _TRACK_REC_CONTEXT_CSS_SELECTOR
            recommendation_regex_pattern = _ARTIST_TRACK_REGEX_PATTERN
        # TODO: also pull the details from <p class="music-recommended-albums-album-context"> to filter based on whether recs are in library or not
        rec_hrefs = [li.get("href") for li in soup.select(rec_class_name)]
        entity_rec_contexts = [elem.text.strip() for elem in soup.select(entity_rec_context_class_name)]
        page_recs: List[LastFMRec] = []
        for i, href_value in enumerate(rec_hrefs):
            regex_match = re.match(recommendation_regex_pattern, href_value)
            artist, entity = regex_match.groups()
            entity_rec_context = RecContext.IN_LIBRARY if entity_rec_contexts[i].endswith("in your library") else RecContext.SIMILAR_ARTIST
            _LOGGER.info(f"artist: {artist}")
            _LOGGER.info(f"{rec_type.value}: {entity}")
            page_recs.append(
                LastFMRec(lastfm_artist_str=artist, lastfm_entity_str=entity, recommendation_type=rec_type, rec_context=entity_rec_context)
            )
        return page_recs
    
    def scrape_recs_list(self, recommendation_type: RecommendationType) -> List[LastFMRec]:
        if self._scraped_recs[recommendation_type] is not None:
            return self._scraped_recs[recommendation_type]
        _LOGGER.info(f"Scraping '{recommendation_type.value}' recommendations from LastFM ...")
        recs: List[LastFMRec] = []
        recs_base_url = _ALBUM_RECS_BASE_URL if recommendation_type == RecommendationType.ALBUM else _TRACK_RECS_BASE_URL
        for page_number in range(1, self._max_rec_pages_to_scrape + 1):
            recs_page_url = f"{recs_base_url}?page={page_number}"
            recs_page_source = self._navigate_to_page_and_get_page_source(url=recs_page_url, rec_type=recommendation_type)
            recs.extend(self._extract_recs_from_page_source(page_source=recs_page_source))
            
        self._scraped_recs[recommendation_type] = recs
        return recs
