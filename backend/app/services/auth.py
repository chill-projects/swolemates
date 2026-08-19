"""WorkOS refresh-token exchange — the one auth call that needs `client_secret`.

The SPA is a PKCE public client for login and never holds a secret. But minting a new
access token from a refresh token goes through WorkOS's `/user_management/authenticate`,
which requires `client_secret` regardless of client type — so this one call has to
happen server-side. Refresh tokens are single-use and rotate on every call; the caller
is responsible for persisting the returned one before the old one stops working.

`_build_client` is the seam tests replace with an `httpx.MockTransport`, matching
`services/food_facts.py`.
"""

import httpx

from app.config import Settings

AUTHENTICATE_URL = "https://api.workos.com/user_management/authenticate"


class RefreshFailed(Exception):
    """WorkOS rejected the token: expired, revoked, already used, or secret unconfigured."""


def _build_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=10.0)


async def refresh_session(settings: Settings, refresh_token: str) -> dict[str, str]:
    """Exchange a refresh token for a new access token + rotated refresh token."""
    if not settings.workos_client_secret:
        raise RefreshFailed("workos_client_secret is not configured")

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
    if response.status_code != 200:
        raise RefreshFailed(response.text)

    body = response.json()
    return {"access_token": body["access_token"], "refresh_token": body["refresh_token"]}
