"""Browser session endpoints — the server-side half of AuthKit for the SPA.

The refresh token is a 7-day credential. It lives in an **httpOnly** cookie, never in
JS: an XSS on the page can't read it, and one tab can't wipe another tab's session.
The short-lived (5-minute) access token still rides in the SPA's `sessionStorage` —
losing that one just means a refresh round-trip.

Flow:
- `POST /auth/session` right after login — the SPA did the PKCE code exchange itself
  (public client, no secret) and hands the resulting refresh token here to be sealed
  into the cookie. Requires the matching access token, so nobody can plant a session.
- `POST /auth/refresh` — reads the cookie, exchanges via WorkOS (needs `client_secret`,
  hence server-side), rotates the cookie, returns the new access token. Status codes
  are load-bearing: 401 means "signed out", 5xx means "try again", and the client must
  only clear its own state on the former.
- `POST /auth/logout` — drops the cookie.
"""

import logging

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import Settings
from app.deps import AppSettings, CurrentUser
from app.services import auth as auth_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Scoped to the auth endpoints — it's never needed anywhere else, so it's never sent
# anywhere else. Keep `_COOKIE_PATH` in sync with this router's mount (`/api` + `/auth`).
REFRESH_COOKIE = "swm_rt"
_COOKIE_PATH = "/api/auth"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days, matching WorkOS's refresh-token lifetime


def _set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=_COOKIE_MAX_AGE,
        path=_COOKIE_PATH,
        httponly=True,
        secure=not settings.is_local,  # http://localhost in dev can't set a Secure cookie
        samesite="lax",
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=_COOKIE_PATH,
        httponly=True,
        secure=not settings.is_local,
        samesite="lax",
    )


class SessionIn(BaseModel):
    refresh_token: str


class AccessTokenOut(BaseModel):
    access_token: str


@router.post("/session", status_code=status.HTTP_204_NO_CONTENT, operation_id="createSession")
async def create_session(body: SessionIn, user_sub: CurrentUser, settings: AppSettings) -> Response:
    """Seal a freshly-issued refresh token into the httpOnly cookie. `CurrentUser` ties
    it to a verified access token so a session can't be planted in someone's browser."""
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _set_refresh_cookie(response, body.refresh_token, settings)
    return response


@router.post("/refresh", operation_id="authRefresh", response_model=AccessTokenOut)
async def refresh(request: Request, settings: AppSettings) -> Response:
    """Rotate the refresh cookie and return a new access token.

    - 401: no cookie, or WorkOS rejected the token → the client signs out.
    - 502: WorkOS unreachable or erroring on its side → the client keeps the session
      and retries later.
    - 500: `client_secret` unconfigured → an ops problem; must *not* read as signed-out.
    """
    cookie = request.cookies.get(REFRESH_COOKIE)
    if not cookie:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": "No session"}
        )

    try:
        result = await auth_service.refresh_session(settings, cookie)
    except auth_service.RefreshRejected as exc:
        log.info("refresh rejected, clearing session: %s", exc)
        rejected = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": "Session expired"}
        )
        _clear_refresh_cookie(rejected, settings)
        return rejected
    except auth_service.RefreshConfigError as exc:
        log.error("refresh misconfigured: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Auth not configured"},
        )
    except auth_service.RefreshUpstreamError as exc:
        log.warning("refresh upstream error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "Auth provider unavailable"},
        )

    ok = JSONResponse(content={"access_token": result["access_token"]})
    _set_refresh_cookie(ok, result["refresh_token"], settings)
    return ok


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, operation_id="logout")
async def logout(settings: AppSettings) -> Response:
    """Drop the refresh cookie. Unauthenticated on purpose — a dead access token must
    still be able to complete a sign-out."""
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(response, settings)
    return response
