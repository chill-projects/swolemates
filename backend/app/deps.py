"""Shared FastAPI dependency aliases.

`Annotated[...]` rather than `= Depends(...)` defaults: same behaviour, but the signature
stays a real type annotation, so linters and type checkers read it correctly.
"""

from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, require_principal, require_user
from app.config import Settings, get_settings
from app.db import get_session
from app.services import profile as profile_service
from app.services.timezones import resolve_timezone

CurrentUser = Annotated[str, Depends(require_user)]
CurrentPrincipal = Annotated[Principal, Depends(require_principal)]
DbSession = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


async def resolve_user_timezone(
    request: Request,
    user_sub: CurrentUser,
    session: DbSession,
) -> ZoneInfo:
    """The caller's timezone for day-boundary logic. A stored `user_profiles.timezone`
    is authoritative — it's what the Settings dropdown writes, and an explicit override
    must apply on the web too, not just the MCP path. Only when it's unset do we fall
    back to the live `X-Timezone` header (the browser's IANA zone, sent on every SPA
    request), then UTC. A malformed header is ignored, not an error.
    See `services/timezones.py`."""
    stored = (await profile_service.get_or_create_profile(session, user_sub)).timezone
    if stored:
        return resolve_timezone(stored)
    header = request.headers.get("X-Timezone")
    if header:
        resolved = resolve_timezone(header)
        if resolved.key != "UTC" or header == "UTC":
            return resolved
    return resolve_timezone(None)


UserTimezone = Annotated[ZoneInfo, Depends(resolve_user_timezone)]
