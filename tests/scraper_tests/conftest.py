import os

import pytest

from tests.conftest import MOCK_HTML_RESPONSES_DIR_PATH

# TODO: ENSURE THE HTML FILES ARE STRIPPED OF SENSISTIVE INFO BEFORE COMMIT!!!
_MOCK_LOGIN_HTML_FILEPATH = os.path.join(MOCK_HTML_RESPONSES_DIR_PATH, "mock_login_page.html")
_MOCK_ALBUM_RECS_PAGE_ONE_FILEPATH = os.path.join(MOCK_HTML_RESPONSES_DIR_PATH, "mock_album_recs_pg_1.html")
# TODO: create the mock track recs html resource file
_MOCK_TRACK_RECS_PAGE_ONE_FILEPATH = os.path.join(MOCK_HTML_RESPONSES_DIR_PATH, "mock_track_recs_pg_1.html")


@pytest.fixture(scope="session")
def login_page_html() -> str:
    with open(_MOCK_LOGIN_HTML_FILEPATH) as f:
        html = f.read()
    return html


@pytest.fixture(scope="session")
def album_recs_page_one_html() -> str:
    with open(_MOCK_ALBUM_RECS_PAGE_ONE_FILEPATH) as f:
        html = f.read()
    return html


@pytest.fixture(scope="session")
def track_recs_page_one_html() -> str:
    with open(_MOCK_TRACK_RECS_PAGE_ONE_FILEPATH) as f:
        html = f.read()
    return html


# TODO: create fixtures for other mocked page HTML entries here
