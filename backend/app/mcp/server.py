"""The MCP front door.

Stateless Streamable HTTP per the 2026-07-28 spec. AuthKitProvider handles discovery,
JWT validation, and audience binding; without it configured (local dev) the server runs
unauthenticated and app.auth.mcp_user_sub() falls back to DEV_USER_SUB.
"""

import logging

from fastmcp import FastMCP

from app.auth import mcp_user_sub
from app.config import get_settings
from app.mcp._icons import app_icons

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


# icons/website_url ride along in `initialize`'s serverInfo — the mark and link Claude
# shows for the connector itself. See app.mcp._icons for why they're URLs.
mcp: FastMCP = FastMCP(
    name="Swolemates",
    website_url=settings.public_url.rstrip("/"),
    icons=app_icons(),
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
