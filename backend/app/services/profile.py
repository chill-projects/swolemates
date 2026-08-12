"""Profile service — one row per user (`user_id` is the primary key, not just a filter).

Reads always get-or-create rather than 404, since a missing profile just means the
defaults haven't been written yet, not that the caller asked for something invalid.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import events
from app.models.profile import UserProfile, WeightUnit


async def get_or_create_profile(session: AsyncSession, user_sub: str) -> UserProfile:
    result = await session.execute(select(UserProfile).where(UserProfile.user_id == user_sub))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = UserProfile(user_id=user_sub)
        session.add(profile)
        await session.flush()
    return profile


async def update_profile(
    session: AsyncSession,
    user_sub: str,
    *,
    weight_unit: WeightUnit | None = None,
    coach_notes: str | None = None,
) -> UserProfile:
    profile = await get_or_create_profile(session, user_sub)
    if weight_unit is not None:
        profile.weight_unit = weight_unit
    if coach_notes is not None:
        profile.coach_notes = coach_notes.strip() or None
    await session.flush()
    events.publish(user_sub, "profile")
    return profile


async def complete_onboarding(session: AsyncSession, user_sub: str) -> UserProfile:
    """Idempotent — set once, never re-triggered by calling this again."""
    profile = await get_or_create_profile(session, user_sub)
    if profile.onboarding_completed_at is None:
        profile.onboarding_completed_at = datetime.now(UTC)
        await session.flush()
        events.publish(user_sub, "profile")
    return profile
