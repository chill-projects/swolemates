"""The MCP front door.

Stateless Streamable HTTP per the 2026-07-28 spec. AuthKitProvider handles discovery,
JWT validation, and audience binding; without it configured (local dev) the server runs
unauthenticated and app.auth.mcp_user_sub() falls back to DEV_USER_SUB.
"""

import logging

from fastmcp import FastMCP
from mcp.types import Icon

from app.auth import mcp_user_sub
from app.config import get_settings

log = logging.getLogger(__name__)

settings = get_settings()


def _auth_provider():
    if not settings.authkit_domain:
        # Production is the only environment that must never run an open MCP endpoint.
        # `test` is allowed to skip it so the suite doesn't need a WorkOS tenant; note
        # that the REST dev bypass stays off there — see tests/test_auth.py.
        if settings.environment == "production":
            raise RuntimeError("AUTHKIT_DOMAIN must be set in production")
        log.warning("MCP server running WITHOUT auth (%s)", settings.environment)
        return None

    from fastmcp.server.auth.providers.workos import AuthKitProvider

    return AuthKitProvider(
        authkit_domain=settings.authkit_domain,
        # base_url becomes the advertised OAuth resource, and clients (claude.ai) POST
        # to whatever the metadata declares — with the bare origin here, Claude POSTed
        # to / and hit the SPA. It must name the actual MCP mount.
        base_url=f"{settings.public_url.rstrip('/')}/mcp",
    )


def _icons() -> list[Icon]:
    """The mark Claude shows beside the connector, from `initialize`'s serverInfo.

    Declaring nothing here is why the connector rendered Railway's logo: with no
    serverInfo.icons a host falls back to whatever it can derive from the hostname,
    which for *.up.railway.app is Railway.

    These are the same PNGs the browser tab and the web manifest use, served from
    PUBLIC_URL by the SPA static handler — one file per size, so the mark only ever
    changes in one place. URLs rather than data: URIs deliberately: the transport is
    stateless, so a client is free to re-`initialize` on every request, and inlining
    ~14 kB of base64 into each of those responses is real weight for an image the
    client will cache after one fetch.

    Both paths are public — an icon is fetched before the OAuth handshake, so an
    authenticated URL would render as a broken image.
    """
    origin = settings.public_url.rstrip("/")
    return [
        Icon(src=f"{origin}/icon-192.png", mimeType="image/png", sizes=["192x192"]),
        Icon(src=f"{origin}/icon-512.png", mimeType="image/png", sizes=["512x512"]),
    ]


mcp: FastMCP = FastMCP(
    name="Swolemates",
    website_url=settings.public_url.rstrip("/"),
    icons=_icons(),
    auth=_auth_provider(),
)


@mcp.tool
async def whoami() -> str:
    """Report which Swolemates account this connection is authenticated as."""
    return f"Authenticated as {mcp_user_sub()}."


# Registers tools/prompts on the server above. Imported for the side effect.
from app.mcp import (  # noqa: E402,F401
    coach_prompt,
    food_facts_tools,
    nutrition_tools,
    planned_workouts_tools,
    profile_tools,
    progress_tools,
    tdee_tools,
    templates_tools,
    workouts_tools,
)
