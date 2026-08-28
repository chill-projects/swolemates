"""WorkOS refresh-token exchange for the Swolemates SPA.

The SPA is a PKCE public client. Login exchanges the authorization code at the AuthKit
domain's `/oauth2/token`, and refresh goes to that *same* endpoint with
`grant_type=refresh_token` — same application, same client_id, no secret. WorkOS's
`/user_management/authenticate` is a different system: it authenticates an AuthKit
application with a client_id + API key pair, which our first-party OAuth application
doesn't have and doesn't need. Pointing refresh there returns `invalid_client` no
matter what secret you supply.

This call still happens server-side so the refresh token can live in an httpOnly
cookie rather than in JS. Refresh tokens are single-use and rotate on every call; the
caller must persist the returned one before the old one stops working. WorkOS allows a
short replay grace window, so a token replayed moments later returns the same rotated
pair rather than an error.

The three failure modes are kept distinct on purpose (see the API layer): a rejected
token means *sign the user out*, but a misconfiguration or a WorkOS outage must not —
otherwise a config slip or an upstream blip logs out every user at once.

`_build_client` is the seam tests replace with an `httpx.MockTransport`, matching
`services/food_facts.py`.
"""

import httpx

from app.config import Settings

# OAuth error codes WorkOS returns when the refresh token itself is no good (expired,
# revoked, or replayed past the rotation grace window). Anything else — a 5xx, a
# network error, `invalid_client` from a credential mismatch — is not the user's
# problem and must not sign them out.
_REJECTION_CODES = {"invalid_grant"}


class RefreshError(Exception):
    """Base for every refresh failure."""


class RefreshRejected(RefreshError):
    """WorkOS rejected the refresh token itself. The session is over — sign out."""


class RefreshConfigError(RefreshError):
    """Client id or AuthKit domain isn't configured. A deploy/ops problem, not the user's."""


class RefreshUpstreamError(RefreshError):
    """WorkOS was unreachable or returned an error unrelated to the token. Transient —
    keep the session and let the caller retry."""


def _build_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=10.0)


def _token_url(settings: Settings) -> str:
    """The token endpoint on our AuthKit domain — the same one login uses."""
    return f"{settings.authkit_domain.rstrip('/')}/oauth2/token"


async def refresh_session(settings: Settings, refresh_token: str) -> dict[str, str]:
    """Exchange a refresh token for a new access token + rotated refresh token.

    Raises `RefreshRejected` / `RefreshConfigError` / `RefreshUpstreamError` — the API
    layer maps each to a different status so the client can tell "signed out" from
    "try again later".
    """
    if not settings.workos_client_id or not settings.authkit_domain:
        raise RefreshConfigError("workos_client_id or authkit_domain is not configured")

    try:
        async with _build_client() as client:
            response = await client.post(
                _token_url(settings),
                # OAuth token endpoints take form encoding, not JSON. `resource` is
                # deliberately absent: WorkOS binds it at the authorize leg and
                # returns invalid_target if a later leg repeats it.
                data={
                    "grant_type": "refresh_token",
                    "client_id": settings.workos_client_id,
                    "refresh_token": refresh_token,
                },
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
    except httpx.HTTPError as exc:
        raise RefreshUpstreamError(f"WorkOS unreachable: {exc}") from exc

    if response.status_code == 200:
        body = response.json()
        access_token = body.get("access_token")
        rotated = body.get("refresh_token")
        if not access_token or not rotated:
            # A 200 without both tokens means the grant didn't carry offline_access.
            # Treat as transient rather than signing the user out over it.
            raise RefreshUpstreamError("WorkOS returned 200 without access_token/refresh_token")
        return {"access_token": access_token, "refresh_token": rotated}

    error_code = ""
    error_description = ""
    try:
        payload = response.json()
        error_code = payload.get("error", "")
        error_description = payload.get("error_description", "")
    except ValueError:
        pass

    if error_code in _REJECTION_CODES:
        raise RefreshRejected(f"WorkOS rejected the refresh token: {error_code}")
    detail = error_code or response.text[:200]
    if error_description:
        detail = f"{detail}: {error_description}"
    raise RefreshUpstreamError(f"WorkOS returned {response.status_code} ({detail})")
