"""
Login-protection middleware enforcing authentication on all routes when `server.auth.enable_login_protection` is on
(a no-op pass-through when it is off).

A request authenticates with a session token issued by a successful login (see
`plastered.api.routes.auth_routes` and `plastered.api.auth_sessions`), presented either as an
`Authorization: Bearer <token>` header (direct API clients) or as the session cookie (browsers).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from fastapi import status
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from plastered.api.auth_sessions import SESSION_COOKIE_NAME

if TYPE_CHECKING:
    from fastapi import Request, Response
    from starlette.middleware.base import RequestResponseEndpoint

# Routes reachable without a session token: the two login flows, plus assets/health probes that carry no user data.
_EXEMPT_PATHS: Final[frozenset[str]] = frozenset({"/api/auth/login", "/login", "/api/healthcheck", "/favicon.ico"})
_EXEMPT_PATH_PREFIXES: Final[tuple[str, ...]] = ("/static/",)


class LoginProtectionMiddleware(BaseHTTPMiddleware):
    """Rejects unauthenticated requests: browsers are redirected to `/login`, API clients get a 401."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        auth_config = request.app.state.lifespan_singleton.app_settings.server.auth
        if not auth_config.enable_login_protection or _is_exempt_path(request.url.path):
            return await call_next(request)
        token = _extract_token(request)
        if token is not None and request.app.state.token_store.is_token_valid(token):
            return await call_next(request)
        if "text/html" in request.headers.get("accept", ""):
            return RedirectResponse(url=f"/login?next={request.url.path}", status_code=status.HTTP_303_SEE_OTHER)
        return JSONResponse(
            content={"detail": "Not authenticated."},
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )


def _is_exempt_path(path: str) -> bool:
    return path in _EXEMPT_PATHS or path.startswith(_EXEMPT_PATH_PREFIXES)


def _extract_token(request: Request) -> str | None:
    """Returns the session token presented by the request: `Authorization: Bearer` header first, cookie fallback."""
    scheme, _, credential = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() == "bearer" and credential.strip():
        return credential.strip()
    return request.cookies.get(SESSION_COOKIE_NAME)
