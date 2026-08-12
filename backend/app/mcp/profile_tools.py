"""Profile tools — no `ui://` component. Onboarding's chat side is a genuine
conversation (#9), not a rendered widget, so these are plain text-returning tools.
"""

from contextlib import asynccontextmanager

from app.auth import mcp_user_sub
from app.db import get_sessionmaker
from app.mcp.server import mcp
from app.models.profile import WeightUnit
from app.services import profile as service


@asynccontextmanager
async def tool_session():
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _summary(profile) -> str:
    onboarded = "yes" if profile.onboarding_completed_at else "not yet"
    notes = profile.coach_notes or "none"
    return (
        f"Weight unit: {profile.weight_unit.value}. "
        f"Onboarding complete: {onboarded}. "
        f"Coach notes: {notes}."
    )


@mcp.tool
async def get_profile() -> str:
    """Read the caller's profile: weight-unit preference, coach notes, onboarding state."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        profile = await service.get_or_create_profile(session, user_sub)
        return _summary(profile)


@mcp.tool
async def update_profile(weight_unit: str | None = None, coach_notes: str | None = None) -> str:
    """Update the caller's weight-unit preference and/or coach notes.

    Args:
        weight_unit: "lbs" or "kg" — display preference only, storage stays canonical lbs.
        coach_notes: Freeform context for coaching (injuries, equipment limits, etc.) —
            replaces any existing notes; pass the full text, not a delta.
    """
    user_sub = mcp_user_sub()
    unit = WeightUnit(weight_unit) if weight_unit is not None else None
    async with tool_session() as session:
        profile = await service.update_profile(
            session, user_sub, weight_unit=unit, coach_notes=coach_notes
        )
        return _summary(profile)


@mcp.tool
async def complete_onboarding() -> str:
    """Mark the caller's welcome/onboarding step as done, so it never shows again."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        profile = await service.complete_onboarding(session, user_sub)
        return _summary(profile)
