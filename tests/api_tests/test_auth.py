import time
from typing import Generator
from unittest.mock import MagicMock, PropertyMock, patch

from fastapi import Response
from fastapi.testclient import TestClient
import pytest

from plastered.api.app import create_fastapi_app
from plastered.api.auth_sessions import SESSION_COOKIE_NAME, SessionTokenStore, credentials_valid, set_session_cookie
from plastered.api.lifespan_resources import LifespanSingleton
from plastered.config.app_settings import AppSettings, AuthConfig
from plastered.utils.exceptions import AppConfigException
from plastered.version import get_project_version

TEST_USERNAME = "admin"
TEST_PASSWORD = "hunter2"


@pytest.fixture(scope="function")
def auth_enabled_client(valid_app_settings: AppSettings) -> Generator[TestClient, None, None]:
    """A TestClient over a fresh app whose settings have `server.auth.enable_login_protection` turned on."""
    auth = AuthConfig(enable_login_protection=True, username=TEST_USERNAME, password=TEST_PASSWORD)
    server = valid_app_settings.server.model_copy(update={"auth": auth})
    app_settings = valid_app_settings.model_copy(update={"server": server})
    singleton = MagicMock(spec=LifespanSingleton)
    type(singleton).app_settings = PropertyMock(return_value=app_settings)
    type(singleton).project_version = PropertyMock(return_value=get_project_version())
    with patch("plastered.api.app.get_lifespan_singleton", return_value=singleton):
        with TestClient(app=create_fastapi_app()) as test_client:
            yield test_client


def _login(client: TestClient, username: str = TEST_USERNAME, password: str = TEST_PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


# ---------------------------------------------------------------------------------------------------------------------
# SessionTokenStore / helpers unit tests
# ---------------------------------------------------------------------------------------------------------------------


def test_token_store_issue_validate_revoke() -> None:
    store = SessionTokenStore()
    token = store.issue_token(session_ttl_hours=1)
    assert store.is_token_valid(token)
    assert not store.is_token_valid("some-other-token")
    store.revoke_token(token)
    assert not store.is_token_valid(token)
    # revoking an unknown token is a no-op
    store.revoke_token(token)


def test_token_store_zero_ttl_never_expires() -> None:
    store = SessionTokenStore()
    token = store.issue_token(session_ttl_hours=0)
    assert store._token_hash_to_expiry[SessionTokenStore._hash_token(token)] is None
    assert store.is_token_valid(token)


def test_token_store_expired_token_dropped() -> None:
    store = SessionTokenStore()
    token = store.issue_token(session_ttl_hours=1)
    # Force the stored expiry into the past instead of monkeypatching the global clock.
    store._token_hash_to_expiry[SessionTokenStore._hash_token(token)] = time.time() - 1
    assert not store.is_token_valid(token)
    # The expired entry was dropped lazily.
    assert store._token_hash_to_expiry == {}


@pytest.mark.parametrize(
    "auth_config_kwargs, username, password, expected",
    [
        ({}, TEST_USERNAME, TEST_PASSWORD, False),  # credentials not configured
        ({"username": TEST_USERNAME, "password": TEST_PASSWORD}, "wrong", TEST_PASSWORD, False),
        ({"username": TEST_USERNAME, "password": TEST_PASSWORD}, TEST_USERNAME, "wrong", False),
        ({"username": TEST_USERNAME, "password": TEST_PASSWORD}, TEST_USERNAME, TEST_PASSWORD, True),
    ],
)
def test_credentials_valid(auth_config_kwargs: dict, username: str, password: str, expected: bool) -> None:
    auth_config = AuthConfig(**auth_config_kwargs)
    assert credentials_valid(auth_config=auth_config, username=username, password=password) is expected


def test_set_session_cookie_zero_ttl_is_session_cookie() -> None:
    response = Response()
    auth_config = AuthConfig(username=TEST_USERNAME, password=TEST_PASSWORD, session_ttl_hours=0)
    set_session_cookie(response=response, raw_token="fake-token", auth_config=auth_config)
    cookie_header = response.headers["set-cookie"]
    assert f"{SESSION_COOKIE_NAME}=fake-token" in cookie_header
    assert "Max-Age" not in cookie_header
    assert "HttpOnly" in cookie_header


def test_auth_config_requires_credentials_when_protection_enabled() -> None:
    with pytest.raises(AppConfigException, match="enable_login_protection"):
        AuthConfig(enable_login_protection=True)


# ---------------------------------------------------------------------------------------------------------------------
# /api/auth/login + /api/auth/logout (JSON API flow)
# ---------------------------------------------------------------------------------------------------------------------


def test_login_success_returns_token_and_sets_cookie(auth_enabled_client: TestClient) -> None:
    resp = _login(auth_enabled_client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["token"]
    assert resp.cookies[SESSION_COOKIE_NAME] == body["token"]


@pytest.mark.parametrize("username, password", [("wrong", TEST_PASSWORD), (TEST_USERNAME, "wrong")])
def test_login_bad_credentials(auth_enabled_client: TestClient, username: str, password: str) -> None:
    resp = _login(auth_enabled_client, username=username, password=password)
    assert resp.status_code == 401


def test_login_not_configured(client: TestClient) -> None:
    """The default example config has no `server.auth` credentials, so login is a 404."""
    resp = _login(client)
    assert resp.status_code == 404


def test_logout_with_bearer_revokes_token(auth_enabled_client: TestClient) -> None:
    token = _login(auth_enabled_client).json()["token"]
    auth_enabled_client.cookies.clear()
    headers = {"Authorization": f"Bearer {token}"}
    assert auth_enabled_client.get("/api/healthcheck", headers=headers).status_code == 200
    resp = auth_enabled_client.post("/api/auth/logout", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"detail": "Logged out."}
    # The token no longer grants access.
    assert auth_enabled_client.get("/api/config", headers=headers).status_code == 401


def test_logout_with_cookie_revokes_token(auth_enabled_client: TestClient) -> None:
    _login(auth_enabled_client)  # session cookie now in the client's jar
    resp = auth_enabled_client.post("/api/auth/logout")
    assert resp.status_code == 200
    # The cookie was deleted and the revoked token no longer grants access.
    assert not auth_enabled_client.cookies
    assert auth_enabled_client.get("/api/config").status_code == 401


def test_logout_without_any_token(client: TestClient) -> None:
    """Logout with no header and no cookie is still a 200 no-op (auth disabled on the default client)."""
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------------------------------------------------
# nav-bar logout control (`POST /logout` browser flow)
# ---------------------------------------------------------------------------------------------------------------------


def test_navbar_logout_control_rendered_when_auth_enabled(auth_enabled_client: TestClient) -> None:
    _login(auth_enabled_client)  # session cookie now in the client's jar
    resp = auth_enabled_client.get("/", headers={"accept": "text/html"})
    assert resp.status_code == 200
    assert 'action="/logout"' in resp.text


def test_navbar_logout_control_hidden_when_auth_disabled(client: TestClient) -> None:
    resp = client.get("/", headers={"accept": "text/html"})
    assert resp.status_code == 200
    assert 'action="/logout"' not in resp.text


def test_browser_logout_revokes_cookie_and_redirects(auth_enabled_client: TestClient) -> None:
    _login(auth_enabled_client)  # session cookie now in the client's jar
    resp = auth_enabled_client.post("/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
    # The cookie was deleted and the revoked token no longer grants access.
    assert not auth_enabled_client.cookies
    assert auth_enabled_client.get("/api/config").status_code == 401


def test_browser_logout_without_cookie(client: TestClient) -> None:
    """Logout with no session cookie is still a redirect no-op (auth disabled on the default client)."""
    resp = client.post("/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


# ---------------------------------------------------------------------------------------------------------------------
# LoginProtectionMiddleware enforcement
# ---------------------------------------------------------------------------------------------------------------------


def test_protected_api_route_requires_token(auth_enabled_client: TestClient) -> None:
    resp = auth_enabled_client.get("/api/config")
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Bearer not-a-real-token"},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Bearer "},
    ],
)
def test_protected_route_rejects_bad_authorization_headers(
    auth_enabled_client: TestClient, headers: dict[str, str]
) -> None:
    assert auth_enabled_client.get("/api/config", headers=headers).status_code == 401


def test_bearer_token_grants_access(auth_enabled_client: TestClient) -> None:
    token = _login(auth_enabled_client).json()["token"]
    auth_enabled_client.cookies.clear()
    resp = auth_enabled_client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_session_cookie_grants_access(auth_enabled_client: TestClient) -> None:
    _login(auth_enabled_client)  # session cookie now in the client's jar
    resp = auth_enabled_client.get("/", headers={"accept": "text/html"})
    assert resp.status_code == 200


def test_unauthenticated_browser_redirected_to_login_page(auth_enabled_client: TestClient) -> None:
    resp = auth_enabled_client.get("/run_history", headers={"accept": "text/html"}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?next=/run_history"


@pytest.mark.parametrize("path", ["/api/healthcheck", "/favicon.ico", "/static/css/classless.css", "/login"])
def test_exempt_paths_do_not_require_token(auth_enabled_client: TestClient, path: str) -> None:
    assert auth_enabled_client.get(path).status_code == 200


# ---------------------------------------------------------------------------------------------------------------------
# /login browser form flow
# ---------------------------------------------------------------------------------------------------------------------


def test_login_page_renders(auth_enabled_client: TestClient) -> None:
    resp = auth_enabled_client.get("/login?next=/adhoc")
    assert resp.status_code == 200
    assert 'name="next" value="/adhoc"' in resp.text


def test_form_login_success_sets_cookie_and_redirects(auth_enabled_client: TestClient) -> None:
    resp = auth_enabled_client.post(
        "/login", data={"username": TEST_USERNAME, "password": TEST_PASSWORD, "next": "/adhoc"}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/adhoc"
    assert resp.cookies[SESSION_COOKIE_NAME]
    # The cookie set by the form login grants access to protected pages.
    assert auth_enabled_client.get("/adhoc", headers={"accept": "text/html"}).status_code == 200


def test_form_login_bad_credentials_rerenders_with_error(auth_enabled_client: TestClient) -> None:
    resp = auth_enabled_client.post("/login", data={"username": TEST_USERNAME, "password": "wrong"})
    assert resp.status_code == 401
    assert "Invalid username or password." in resp.text
    assert SESSION_COOKIE_NAME not in resp.cookies


def test_form_login_sanitizes_unsafe_next_url(auth_enabled_client: TestClient) -> None:
    resp = auth_enabled_client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD, "next": "//evil.example.com/phish"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
