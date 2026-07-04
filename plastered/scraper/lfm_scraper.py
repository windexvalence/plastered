import logging
import re
from random import randint
from time import sleep
from typing import Any

from bs4 import BeautifulSoup
from rebrowser_playwright.sync_api import BrowserType, Error, Page, Playwright, sync_playwright

from plastered.config.app_settings import AppSettings
from plastered.models import CacheType, EntityType, LFMRec, RecContext
from plastered.run_cache.run_cache import RunCache
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
from plastered.utils.exceptions import ScraperException
from plastered.utils.log_utils import CONSOLE, SPINNER

_LOGGER = logging.getLogger(__name__)

_ARTIST_ALBUM_REGEX_PATTERN = re.compile(r"^\/music\/([^\/]+)\/(.+)$")
_ARTIST_TRACK_REGEX_PATTERN = re.compile(r"^\/music\/([^\/]+)\/_\/(.+)$")

# Last.fm can trigger a client-side navigation between the rec list appearing and the page-source read, which makes
# `page.content()` raise "Unable to retrieve content because the page is navigating and changing the content". We wait
# for the in-flight navigation to settle and retry a bounded number of times.
_PAGE_NAVIGATING_ERR_FRAGMENT = "navigating and changing the content"
_CONTENT_READ_MAX_ATTEMPTS = 3
# How long to wait for the page's network to go idle (i.e. an in-flight navigation to finish) between content-read
# attempts. Bounded so a page with persistent connections that never reaches networkidle doesn't hang the scrape.
_PAGE_SETTLE_TIMEOUT_MS = 5000


def _sleep_random() -> None:
    """
    Very dumb utility function to sleep a bounded random number of seconds between playwright client interactions with the LFM site to reduce predictability.
    """
    sleep_seconds = randint(RENDER_WAIT_SEC_MIN, RENDER_WAIT_SEC_MAX)  # nosec B311
    _LOGGER.debug(f"Sleeping for {sleep_seconds} before continuing ...")
    sleep(sleep_seconds)


# TODO (later): refactor this as a dataclass in a separate file
def cached_lfm_recs_validator(cached_data: Any) -> bool:
    """
    Passed to the RunCache.load_from_cache_if_valid method when attempting loads of cached LFM recs.
    """
    return isinstance(cached_data, list) and all([isinstance(elem, LFMRec) for elem in cached_data])


class LFMRecsScraper:
    """
    Utility class which manages the headless browser-based interactions with the recommendations pages to gather the recommendation data for subsequent searching and processing.
    """

    def __init__(self, app_settings: AppSettings, rec_types_to_scrape_override: list[EntityType] | None = None):
        self._max_rec_pages_to_scrape = app_settings.lfm.scraper_max_rec_pages_to_scrape
        self._lfm_username = app_settings.lfm.lfm_username
        self._lfm_password = app_settings.lfm.lfm_password.get_secret_value()
        self._rec_types_to_scrape = rec_types_to_scrape_override or [
            EntityType(rec_type) for rec_type in app_settings.lfm.rec_types_to_scrape
        ]
        self._run_cache = RunCache(app_settings=app_settings, cache_type=CacheType.SCRAPER)
        self._loaded_from_run_cache: dict[EntityType, list[LFMRec] | None] = {rec_type: None for rec_type in EntityType}
        self._is_logged_in = False
        self._playwright: Playwright | None = None
        self._browser: BrowserType | None = None
        self._page: Page | None = None

    def __enter__(self):
        for rec_type in self._rec_types_to_scrape:
            self._loaded_from_run_cache[rec_type] = self._run_cache.load_data_if_valid(
                cache_key=rec_type.value, data_validator_fn=cached_lfm_recs_validator
            )
        if all([cached_recs is not None for _, cached_recs in self._loaded_from_run_cache.items()]):
            _LOGGER.info("Scraper cache enabled and cache hit successful for all enabled rec types.")
            _LOGGER.info("Skipping scraper browser initialization.")
            return self
        with CONSOLE.status("Initializing LFM scraper ...", spinner=SPINNER):
            _LOGGER.info("Initializing LFM scraper ...")
            self._playwright = sync_playwright().start()
            _LOGGER.info("Initializing headless chromium browser ...")
            self._browser = self._playwright.chromium.launch(headless=True)
            _LOGGER.info("Opening new page in headless chromium browser ...")
            self._page = self._browser.new_page(user_agent=PW_USER_AGENT)
            if self._page is None:  # pragma: no cover
                msg = "Unable to open a new page in playwright browser. Exiting."
                _LOGGER.error(msg)
                raise ScraperException(msg)
            _LOGGER.info("Attempting Last.fm user login ...")
            self._user_login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:  # pragma: no cover
            _LOGGER.error(f"Scraper encountered an uncaught exception: {exc_val}")
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
        if not self._page:  # pragma: no cover
            raise ScraperException("Page is not initialized")
        _LOGGER.debug("Attempting login ...")
        _LOGGER.info("Accessing login url ...")
        self._page.goto(LOGIN_URL, wait_until="domcontentloaded")
        _LOGGER.debug("Locating username form ...")
        self._page.locator(LOGIN_USERNAME_FORM_LOCATOR).fill(self._lfm_username)
        _LOGGER.debug("Locating password form ...")
        self._page.locator(LOGIN_PASSWORD_FORM_LOCATOR).fill(self._lfm_password)
        _LOGGER.debug("Locating login button ...")
        self._page.locator(LOGIN_BUTTON_LOCATOR).click()
        _LOGGER.info("Waiting for successful login ...")
        _LOGGER.debug("Calling sleep_random ...")
        _sleep_random()
        self._is_logged_in = True
        _LOGGER.debug(f"Current driver page URL: {self._page.url}")

    def _user_logout(self) -> None:
        if not self._page:  # pragma: no cover
            raise ScraperException("Page is not initialized")
        _LOGGER.debug("Logging out from last.fm account ...")
        self._page.goto(LOGOUT_URL, wait_until="domcontentloaded")
        self._page.get_by_role("button", name=re.compile("logout", re.IGNORECASE)).locator("visible=true").first.click()
        self._is_logged_in = False

    def _navigate_to_page_and_get_page_source(self, url: str, rec_type: EntityType) -> str:
        if not self._page:  # pragma: no cover
            raise ScraperException("Page is not initialized")
        _LOGGER.info(f"Rendering {url} page source ...")
        self._page.goto(url, wait_until="domcontentloaded")
        wait_css_selector = (
            ALBUM_REC_LIST_ELEMENT_CSS_SELECTOR if rec_type == EntityType.ALBUM else TRACK_REC_LIST_ELEMENT_CSS_SELECTOR
        )
        recs_page_locator = self._page.locator(wait_css_selector)  # pylint: disable=unused-variable
        recs_page_locator.first.wait_for()
        _sleep_random()
        return self._read_page_content(page=self._page)

    @staticmethod
    def _read_page_content(page: Page) -> str:
        """
        Returns the page's HTML, retrying if Last.fm triggers a navigation while the content is being read.
        `page.content()` raises "Unable to retrieve content because the page is navigating and changing the content"
        in that window (the tracks recommendations page in particular kicks off a client-side navigation shortly after
        it loads). Between attempts we wait for the network to go idle so the in-flight navigation actually finishes
        before retrying — a plain `wait_for_load_state()` returns immediately here because the original document already
        fired its load event. Non-navigation errors (and a still-navigating page after the final attempt) are re-raised.
        """
        for attempt in range(_CONTENT_READ_MAX_ATTEMPTS):
            try:
                return page.content()
            except Error as err:
                is_last_attempt = attempt == _CONTENT_READ_MAX_ATTEMPTS - 1
                if _PAGE_NAVIGATING_ERR_FRAGMENT not in str(err) or is_last_attempt:
                    raise
                _LOGGER.warning(
                    f"Page navigating while reading content (attempt {attempt + 1}); "
                    "waiting for network idle and retrying ..."
                )
                try:
                    page.wait_for_load_state("networkidle", timeout=_PAGE_SETTLE_TIMEOUT_MS)
                except Error:
                    # networkidle may never be reached (persistent connections) or the page may still be churning;
                    # proceed anyway and let the next content() attempt try again.
                    _LOGGER.debug("Page did not reach network idle before timeout; retrying content read anyway.")
        raise ScraperException("Exhausted page-content read attempts")  # pragma: no cover

    def _extract_recs_from_page_source(self, page_source: str, rec_type: EntityType) -> list[LFMRec]:
        soup = BeautifulSoup(page_source, "html.parser")
        if rec_type == EntityType.ALBUM:
            rec_class_name = ALBUM_REC_LIST_ELEMENT_BS4_CSS_SELECTOR
            entity_rec_context_class_name = ALBUM_REC_CONTEXT_BS4_CSS_SELECTOR
            recommendation_regex_pattern = _ARTIST_ALBUM_REGEX_PATTERN
        else:
            rec_class_name = TRACK_REC_LIST_ELEMENT_BS4_CSS_SELECTOR
            entity_rec_context_class_name = TRACK_REC_CONTEXT_CSS_SELECTOR
            recommendation_regex_pattern = _ARTIST_TRACK_REGEX_PATTERN

        rec_hrefs = [li.get("href") for li in soup.select(rec_class_name)]
        entity_rec_contexts = [elem.text.strip() for elem in soup.select(entity_rec_context_class_name)]
        page_recs: list[LFMRec] = []
        for i, href_value in enumerate(rec_hrefs):
            regex_match = re.match(recommendation_regex_pattern, href_value)  # type: ignore
            if not regex_match:  # pragma: no cover
                continue
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

    def _scrape_recs_list(self, rec_type: EntityType) -> list[LFMRec]:
        if cached_list := self._loaded_from_run_cache.get(rec_type):
            return cached_list
        _LOGGER.info(f"Scraping '{rec_type.value}' recommendations from LFM ...")
        recs: list[LFMRec] = []
        recs_base_url = ALBUM_RECS_BASE_URL if rec_type == EntityType.ALBUM else TRACK_RECS_BASE_URL
        for page_number in range(1, self._max_rec_pages_to_scrape + 1):
            recs_page_url = f"{recs_base_url}?page={page_number}"
            recs_page_source = self._navigate_to_page_and_get_page_source(url=recs_page_url, rec_type=rec_type)
            recs.extend(self._extract_recs_from_page_source(page_source=recs_page_source, rec_type=rec_type))
        if self._run_cache.enabled:
            _LOGGER.debug("Attempting cache write for scraper ...")
            cache_write_success = self._run_cache.write_data(cache_key=rec_type.value, data=recs)
            _LOGGER.debug(f"Scraper cache write: {cache_write_success}")
        return recs

    def scrape_recs(self) -> dict[EntityType, list[LFMRec]]:
        return {rec_type: self._scrape_recs_list(rec_type=rec_type) for rec_type in self._rec_types_to_scrape}
