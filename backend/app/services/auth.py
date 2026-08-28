"""WorkOS refresh-token exchange — the one auth call that needs `client_secret`.

The SPA is a PKCE public client for login and never holds a secret. But minting a new
access token from a refresh token goes through WorkOS's `/user_management/authenticate`,
which requires `client_secret` regardless of client type — so this one call has to
happen server-side. Refresh tokens are single-use and rotate on every call; the caller
is responsible for persisting the returned one before the old one stops working.

The three failure modes are kept distinct on purpose (see the API layer): a rejected
token means *sign the user out*, but a missing secret or a WorkOS outage must not —
otherwise a config slip or an upstream blip logs out every user at once.

`_build_client` is the seam tests replace with an `httpx.MockTransport`, matching
`services/food_facts.py`.
"""

import httpx

from app.config import Settings

AUTHENTICATE_URL = "https://api.workos.com/user_management/authenticate"

# OAuth error codes WorkOS returns when the refresh token itself is no good (expired,
# revoked, or replayed past the rotation grace window). Anything else — a 5xx, a
# network error, a 401 from bad client credentials — is not the user's problem.
_REJECTION_CODES = {"invalid_grant"}


class RefreshError(Exception):
    """Base for every refresh failure."""


class RefreshRejected(RefreshError):
    """WorkOS rejected the refresh token itself. The session is over — sign out."""


class RefreshConfigError(RefreshError):
    """`client_secret` isn't configured. A deploy/ops problem, not the user's."""


class RefreshUpstreamError(RefreshError):
    """WorkOS was unreachable or returned an error unrelated to the token. Transient —
    keep the session and let the caller retry."""


def _build_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=10.0)


async def refresh_session(settings: Settings, refresh_token: str) -> dict[str, str]:
    """Exchange a refresh token for a new access token + rotated refresh token.

    Raises `RefreshRejected` / `RefreshConfigError` / `RefreshUpstreamError` — the API
    layer maps each to a different status so the client can tell "signed out" from
    "try again later".
    """
    if not settings.workos_client_secret:
        raise RefreshConfigError("workos_client_secret is not configured")

    try:
        async with _build_client() as client:
            response = await client.post(
                AUTHENTICATE_URL,
                json={
                    "client_id": settings.workos_client_id,
                    "client_secret": settings.workos_client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
    except httpx.HTTPError as exc:
        raise RefreshUpstreamError(f"WorkOS unreachable: {exc}") from exc

    if response.status_code == 200:
        body = response.json()
        return {"access_token": body["access_token"], "refresh_token": body["refresh_token"]}

    error_code = ""
    try:
        error_code = response.json().get("error", "")
    except ValueError:
        pass

    if error_code in _REJECTION_CODES:
        raise RefreshRejected(f"WorkOS rejected the refresh token: {error_code}")
    raise RefreshUpstreamError(
        f"WorkOS returned {response.status_code} ({error_code or response.text[:200]})"
    )
