import logging
import re
from enum import StrEnum
from random import randint
from time import sleep
from typing import Any, Dict, List, Optional, Union
from urllib.parse import quote_plus, unquote_plus

from bs4 import BeautifulSoup
from rebrowser_playwright.sync_api import BrowserType, Page, Playwright, sync_playwright
from tqdm import trange
from tqdm.contrib.logging import logging_redirect_tqdm

from plastered.config.config_parser import AppConfig
from plastered.run_cache.run_cache import CacheType, RunCache
from plastered.utils.constants import (
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
    RENDER_WAIT_SEC_MAX,
    RENDER_WAIT_SEC_MIN,
    TRACK_REC_CONTEXT_CSS_SELECTOR,
    TRACK_REC_LIST_ELEMENT_BS4_CSS_SELECTOR,
    TRACK_REC_LIST_ELEMENT_CSS_SELECTOR,
    TRACK_RECS_BASE_URL,
)
from plastered.utils.exceptions import LFMRecException

_LOGGER = logging.getLogger(__name__)

_ARTIST_ALBUM_REGEX_PATTERN = re.compile(r"^\/music\/([^\/]+)\/(.+)$")
_ARTIST_TRACK_REGEX_PATTERN = re.compile(r"^\/music\/([^\/]+)\/_\/(.+)$")


class RecommendationType(StrEnum):
    """
    Enum representing the type of LFM recommendation. Can be either "album", or "track" currently.
    """

    ALBUM = "album"
    TRACK = "track"


class RecContext(StrEnum):
    """
    Enum representing the recommendation's context, as stated by LFM's recommendation page.
    Can be either "in-library", or "similar-artist".

    "in-library" means that the recommendation is for a release from an artist which is already in your library, according to LFM.
    "similar-artist" means that the recommendation is for a release from an artist which is similar to other artists you frequently listen to, according to LFM.
    """

    IN_LIBRARY = "in-library"
    SIMILAR_ARTIST = "similar-artist"


def _sleep_random() -> None:
    """
    Very dumb utility function to sleep a bounded random number of seconds between playwright client interactions with the LFM site to reduce predictability.
    """
    sleep_seconds = randint(RENDER_WAIT_SEC_MIN, RENDER_WAIT_SEC_MAX)  # nosec B311
    _LOGGER.debug(f"Sleeping for {sleep_seconds} before continuing ...")
    sleep(sleep_seconds)


class LFMRec:
    """
    Class representing a singular recommendation from LFM.
    Corresponds to either a distinct LFM Album recommendation, or a distinct LFM Track recommendation.
    """

    def __init__(
        self,
        lfm_artist_str: str,
        lfm_entity_str: str,
        recommendation_type: Union[str, RecommendationType],
        rec_context: Union[str, RecContext],
    ):
        self._lfm_artist_str = lfm_artist_str
        self._lfm_entity_str = lfm_entity_str
        self._recommendation_type = RecommendationType(recommendation_type)
        self._rec_context = RecContext(rec_context)
        self._track_origin_release: Optional[str] = None
        self._track_origin_release_mbid: Optional[str] = None

    def __str__(self) -> str:
        return f"artist={self._lfm_artist_str}, {self._recommendation_type.value}={self._lfm_entity_str}, context={self._rec_context.value}"

    def __eq__(self, other) -> bool:
        if not isinstance(other, LFMRec):
            return False
        return (
            self.artist_str == other.artist_str
            and self.entity_str == other.entity_str
            and self.is_album_rec() == other.is_album_rec()
            and self.rec_context.value == other.rec_context.value
        )

    def set_track_origin_release(self, track_origin_release: str) -> None:
        """Set the release that the track rec originated from. Only used for RecommendationType.TRACK instances."""
        if not self.is_track_rec():
            raise LFMRecException(
                f"Cannot set the track_origin_release on a LFMRec instance with a {self._recommendation_type.value} reccommendation type."
            )
        self._track_origin_release = quote_plus(track_origin_release)

    def set_track_origin_release_mbid(self, track_origin_release_mbid) -> None:
        """Set the MBID of the release which the track rec originated from. Only used for RecommendationType.TRACK instances."""
        if not self.is_track_rec():
            raise LFMRecException(
                f"Cannot set the track_origin_release_mbid on a LFMRec instance with a {self._recommendation_type.value} reccommendation type."
            )
        self._track_origin_release_mbid = track_origin_release_mbid

    def is_album_rec(self) -> bool:
        return self._recommendation_type == RecommendationType.ALBUM

    def is_track_rec(self) -> bool:
        return self._recommendation_type == RecommendationType.TRACK

    @property
    def artist_str(self) -> str:
        return self._lfm_artist_str

    def get_human_readable_artist_str(self) -> str:
        return unquote_plus(self._lfm_artist_str)

    def get_human_readable_release_str(self) -> str:
        if self.is_track_rec():
            return unquote_plus(self._track_origin_release)
        return unquote_plus(self._lfm_entity_str)

    def get_human_readable_entity_str(self) -> str:
        return unquote_plus(self._lfm_entity_str)

    def get_human_readable_track_str(self) -> str:
        if not self.is_track_rec():
            raise LFMRecException(
                f"Cannot get the track name from an LFMRec instance with a {self._recommendation_type.value} reccommendation type."
            )
        return unquote_plus(self._lfm_entity_str)

    def get_human_readable_track_origin_release_str(self) -> Optional[str]:
        if not self.is_track_rec():
            raise LFMRecException(
                f"Cannot get the track_origin_release from an LFMRec instance with a {self._recommendation_type.value} reccommendation type."
            )
        return unquote_plus(self._track_origin_release)

    @property
    def entity_str(self) -> str:
        return self._lfm_entity_str

    @property
    def release_str(self) -> str:
        return (
            self._lfm_entity_str
            if self._recommendation_type == RecommendationType.ALBUM
            else self._track_origin_release
        )

    @property
    def rec_type(self) -> RecommendationType:
        return self._recommendation_type

    @property
    def rec_context(self) -> RecContext:
        return self._rec_context

    @property
    def lfm_entity_url(self) -> str:
        if self._recommendation_type == RecommendationType.ALBUM:
            return f"https://www.last.fm/music/{self._lfm_artist_str}/{self._lfm_entity_str}"
        return f"https://www.last.fm/music/{self._lfm_artist_str}/_/{self._lfm_entity_str}"

    @property
    def track_origin_release_mbid(self) -> str:
        if not self.is_track_rec():
            raise LFMRecException(
                f"Cannot get the track_origin_release_mbid from an LFMRec instance with a {self._recommendation_type.value} reccommendation type."
            )
        return self._track_origin_release_mbid


def cached_lfm_recs_validator(cached_data: Any) -> bool:
    """
    Passed to the RunCache.load_from_cache_if_valid method when attempting loads of cached LFM recs.
    """
    return isinstance(cached_data, list) and all([isinstance(elem, LFMRec) for elem in cached_data])


class LFMRecsScraper:
    """
    Utility class which manages the headless browser-based interactions with the recommendations pages to gather the recommendation data for subsequent searching and processing.
    """

    def __init__(self, app_config: AppConfig):
        self._max_rec_pages_to_scrape = app_config.get_cli_option("scraper_max_rec_pages_to_scrape")
        self._lfm_username = app_config.get_cli_option("lfm_username")
        self._lfm_password = app_config.get_cli_option("lfm_password")
        self._rec_types_to_scrape = [
            RecommendationType(rec_type) for rec_type in app_config.get_cli_option("rec_types_to_scrape")
        ]
        self._run_cache = RunCache(app_config=app_config, cache_type=CacheType.SCRAPER)
        self._loaded_from_run_cache: Dict[RecommendationType, Optional[List[LFMRec]]] = {
            rec_type: None for rec_type in RecommendationType
        }
        self._login_success_url = f"https://www.last.fm/user/{self._lfm_username}"
        self._is_logged_in = False
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[BrowserType] = None
        self._page: Optional[Page] = None

    def __enter__(self):
        for rec_type in self._rec_types_to_scrape:
            self._loaded_from_run_cache[rec_type] = self._run_cache.load_data_if_valid(
                cache_key=rec_type.value,
                data_validator_fn=cached_lfm_recs_validator,
            )
        if all([cached_recs is not None for _, cached_recs in self._loaded_from_run_cache.items()]):
            _LOGGER.info(f"Scraper cache enabled and cache hit successful for all enabled rec types.")
            _LOGGER.info(f"Skipping scraper browser initialization.")
            return self
        _LOGGER.info(f"Initializing scraper ...")
        self._playwright = sync_playwright().start()
        _LOGGER.info(f"Initializing headless chromium browser ...")
        self._browser = self._playwright.chromium.launch(headless=True)
        _LOGGER.info(f"Opening new page in headless chromium browser ...")
        self._page = self._browser.new_page(user_agent=PW_USER_AGENT)
        _LOGGER.info(f"Attempting Last.fm user login ...")
        self._user_login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:  # pragma: no cover
            _LOGGER.error("Scraper encountered an uncaught exception", exc_info=True)
        self._run_cache.close()
        if self._is_logged_in:
            self._user_logout()
        if self._page:
            self._page.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def _user_login(self) -> None:
        _LOGGER.debug(f"Attempting login ...")
        _LOGGER.info(f"Accessing login url ...")
        self._page.goto(LOGIN_URL, wait_until="domcontentloaded")
        _LOGGER.debug(f"Locating username form ...")
        self._page.locator(LOGIN_USERNAME_FORM_LOCATOR).fill(self._lfm_username)
        _LOGGER.debug(f"Locating password form ...")
        self._page.locator(LOGIN_PASSWORD_FORM_LOCATOR).fill(self._lfm_password)
        _LOGGER.debug(f"Locating login button ...")
        self._page.locator(LOGIN_BUTTON_LOCATOR).click()
        _LOGGER.info(f"Waiting for successful login ...")
        _LOGGER.debug(f"Calling sleep_random ...")
        _sleep_random()
        self._is_logged_in = True
        _LOGGER.debug(f"Current driver page URL: {self._page.url}")

    def _user_logout(self) -> None:
        _LOGGER.debug(f"Logging out from last.fm account ...")
        self._page.goto(LOGOUT_URL, wait_until="domcontentloaded")
        self._page.get_by_role("button", name=re.compile("logout", re.IGNORECASE)).locator("visible=true").first.click()
        self._is_logged_in = False

    def _navigate_to_page_and_get_page_source(self, url: str, rec_type: RecommendationType) -> str:
        _LOGGER.info(f"Rendering {url} page source ...")
        self._page.goto(url, wait_until="domcontentloaded")
        wait_css_selector = (
            ALBUM_REC_LIST_ELEMENT_CSS_SELECTOR
            if rec_type == RecommendationType.ALBUM
            else TRACK_REC_LIST_ELEMENT_CSS_SELECTOR
        )
        recs_page_locator = self._page.locator(wait_css_selector)  # pylint: disable=unused-variable
        _sleep_random()
        return self._page.content()

    def _extract_recs_from_page_source(self, page_source: str, rec_type: RecommendationType) -> List[LFMRec]:
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
        page_recs: List[LFMRec] = []
        for i, href_value in enumerate(rec_hrefs):
            regex_match = re.match(recommendation_regex_pattern, href_value)
            artist, entity = regex_match.groups()
            entity_rec_context = (
                RecContext.IN_LIBRARY
                if entity_rec_contexts[i].endswith("in your library")
                else RecContext.SIMILAR_ARTIST
            )
            _LOGGER.debug(f"artist: {artist}")
            _LOGGER.debug(f"{rec_type.value}: {entity}")
            page_recs.append(
                LFMRec(
                    lfm_artist_str=artist,
                    lfm_entity_str=entity,
                    recommendation_type=rec_type,
                    rec_context=entity_rec_context,
                )
            )
        return page_recs

    def _scrape_recs_list(self, rec_type: RecommendationType) -> List[LFMRec]:
        if self._loaded_from_run_cache[rec_type]:
            return self._loaded_from_run_cache[rec_type]
        _LOGGER.info(f"Scraping '{rec_type.value}' recommendations from LFM ...")
        recs: List[LFMRec] = []
        recs_base_url = ALBUM_RECS_BASE_URL if rec_type == RecommendationType.ALBUM else TRACK_RECS_BASE_URL
        # needed to make sure tqdm doesn't break logging: https://stackoverflow.com/a/69145493
        with logging_redirect_tqdm(loggers=[_LOGGER]):
            for page_number in trange(1, self._max_rec_pages_to_scrape + 1, desc=f"{rec_type.value} recs scraping"):
                recs_page_url = f"{recs_base_url}?page={page_number}"
                recs_page_source = self._navigate_to_page_and_get_page_source(url=recs_page_url, rec_type=rec_type)
                recs.extend(self._extract_recs_from_page_source(page_source=recs_page_source, rec_type=rec_type))
        if self._run_cache.enabled:
            _LOGGER.info(f"Attempting cache write for scraper ...")
            cache_write_success = self._run_cache.write_data(cache_key=rec_type.value, data=recs)
            _LOGGER.info(f"Scraper cache write: {cache_write_success}")
        return recs

    def scrape_recs(self) -> Dict[RecommendationType, List[LFMRec]]:
        return {rec_type: self._scrape_recs_list(rec_type=rec_type) for rec_type in self._rec_types_to_scrape}
