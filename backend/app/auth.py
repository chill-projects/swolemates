"""Token verification for both front doors.

Both transports resolve to the same thing: a WorkOS `sub` string. The MCP side is
verified by FastMCP's AuthKitProvider; the REST side is verified here against AuthKit's
JWKS. Everything downstream takes `user_sub: str` and never knows which door it came in.
"""

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKClient

from app.config import Settings, get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Principal:
    sub: str
    claims: dict


@lru_cache
def _jwk_client(authkit_domain: str) -> PyJWKClient:
    # PyJWKClient caches keys and refetches on unknown kid, so this survives key rotation.
    return PyJWKClient(f"{authkit_domain.rstrip('/')}/oauth2/jwks")


def verify_bearer_token(token: str, settings: Settings) -> Principal:
    """Verify an AuthKit-issued JWT and return its subject.

    Audience is bound to our own public URL — a token minted for some other resource
    server must not work here. This is the check the design doc calls out as easy to
    forget, so it is not optional.
    """
    if not settings.authkit_domain:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AUTHKIT_DOMAIN is not configured",
        )
    signing_key = _jwk_client(settings.authkit_domain).get_signing_key_from_jwt(token)
    try:
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.public_url,
            issuer=settings.authkit_domain.rstrip("/"),
        )
    except jwt.PyJWTError as exc:
        log.warning("rejected bearer token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has no subject")
    return Principal(sub=sub, claims=claims)


async def require_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    """FastAPI dependency resolving the request to a WorkOS `sub`.

    In local dev only, an absent Authorization header falls back to DEV_USER_SUB so the
    dev loop doesn't need an OAuth round trip for every call. Any other environment
    returns 401 — see test_dev_bypass_is_inert_outside_local.
    """
    header = request.headers.get("Authorization", "")
    if not header:
        if settings.is_local:
            return settings.dev_user_sub
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expected 'Authorization: Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_bearer_token(token, settings).sub


def mcp_user_sub() -> str:
    """The MCP-side equivalent of require_user().

    AuthKitProvider has already verified signature and audience by the time a tool runs;
    we only pull the subject back out.
    """
    from fastmcp.server.dependencies import get_access_token

    settings = get_settings()
    token = get_access_token()
    if token is None:
        if settings.is_local:
            return settings.dev_user_sub
        raise PermissionError("This tool requires an authenticated user.")

    sub = token.claims.get("sub")
    if not sub:
        raise PermissionError("Access token has no subject.")
    return sub
