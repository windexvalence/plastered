"""
Session-token primitives shared by the login/logout routes (`plastered.api.routes.auth_routes`, the `/login` page in
`webserver_routes`) and the login-protection middleware (`plastered.api.middleware`).

Tokens are opaque random strings issued by a successful login. The server keeps only a SHA-256 digest of each issued
token in memory, so a leaked process dump never reveals a usable credential. The store is in-memory and per-process,
which is correct for plastered's single-worker server model (see `ServerConfig.workers`): restarting the server simply
requires clients to log in again.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Response

    from plastered.config.app_settings import AuthConfig

SESSION_COOKIE_NAME = "plastered_session"
_SECONDS_PER_HOUR = 3600


class SessionTokenStore:
    """In-memory registry of the active login-session tokens (stored hashed) and their expiration timestamps."""

    def __init__(self) -> None:
        # token sha256 hexdigest -> unix expiry timestamp (None = never expires, i.e. `session_ttl_hours` == 0).
        self._token_hash_to_expiry: dict[str, float | None] = {}

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    def issue_token(self, session_ttl_hours: int) -> str:
        """Creates, registers, and returns a new session token expiring `session_ttl_hours` from now (0 = never)."""
        raw_token = secrets.token_urlsafe(32)
        expiry = time.time() + session_ttl_hours * _SECONDS_PER_HOUR if session_ttl_hours > 0 else None
        self._token_hash_to_expiry[self._hash_token(raw_token)] = expiry
        return raw_token

    def is_token_valid(self, raw_token: str) -> bool:
        """True while `raw_token` is a registered, unexpired session token. Expired tokens are dropped lazily here."""
        token_hash = self._hash_token(raw_token)
        if token_hash not in self._token_hash_to_expiry:
            return False
        expiry = self._token_hash_to_expiry[token_hash]
        if expiry is not None and expiry < time.time():
            del self._token_hash_to_expiry[token_hash]
            return False
        return True

    def revoke_token(self, raw_token: str) -> None:
        """Removes `raw_token` from the registry (a no-op for unknown tokens)."""
        self._token_hash_to_expiry.pop(self._hash_token(raw_token), None)


def credentials_valid(auth_config: AuthConfig, username: str, password: str) -> bool:
    """Constant-time comparison of a login attempt against the configured `server.auth` credentials."""
    if auth_config.username is None or auth_config.password is None:
        return False
    username_ok = secrets.compare_digest(username.encode(), auth_config.username.get_secret_value().encode())
    password_ok = secrets.compare_digest(password.encode(), auth_config.password.get_secret_value().encode())
    return username_ok and password_ok


def set_session_cookie(response: Response, raw_token: str, auth_config: AuthConfig) -> None:
    """
    Attaches the session-token cookie browsers authenticate with. `secure` is intentionally not set: the server
    commonly runs plain-HTTP on a LAN or behind a TLS-terminating reverse proxy.
    """
    max_age = auth_config.session_ttl_hours * _SECONDS_PER_HOUR or None  # 0 (no expiry) -> session cookie
    response.set_cookie(key=SESSION_COOKIE_NAME, value=raw_token, max_age=max_age, httponly=True, samesite="lax")
