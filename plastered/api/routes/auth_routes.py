from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from plastered.api.api_models import LoginRequestBody, LoginResponseBody, LogoutResponseBody
from plastered.api.auth_sessions import SESSION_COOKIE_NAME, credentials_valid, set_session_cookie
from plastered.api.constants import RouterPrefix
from plastered.api.fastapi_dependencies import AppSettingsDep

auth_router = APIRouter(prefix=f"{RouterPrefix.API}/auth", tags=["auth"])

_bearer_scheme = HTTPBearer(auto_error=False)
BearerCredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)]


@auth_router.post("/login")
async def login(
    login_body: LoginRequestBody, app_settings: AppSettingsDep, request: Request, response: Response
) -> LoginResponseBody:
    """Exchange the login credentials for a bearer token (also set as the session cookie for browser clients)."""
    auth_config = app_settings.server.auth
    if auth_config.username is None or auth_config.password is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Login is not configured; set `server.auth.username` and `server.auth.password`.",
        )
    if not credentials_valid(
        auth_config=auth_config,
        username=login_body.username.get_secret_value(),
        password=login_body.password.get_secret_value(),
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")
    token = request.app.state.token_store.issue_token(session_ttl_hours=auth_config.session_ttl_hours)
    set_session_cookie(response=response, raw_token=token, auth_config=auth_config)
    return LoginResponseBody(token=token)


@auth_router.post("/logout")
async def logout(request: Request, response: Response, credentials: BearerCredentialsDep) -> LogoutResponseBody:
    """Revoke the bearer token this request authenticated with (`Authorization` header or session cookie)."""
    token = credentials.credentials if credentials is not None else request.cookies.get(SESSION_COOKIE_NAME)
    if token is not None:
        request.app.state.token_store.revoke_token(token)
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return LogoutResponseBody()
