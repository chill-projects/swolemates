"""Profile service — one row per user (`user_id` is the primary key, not just a filter).

Reads always get-or-create rather than 404, since a missing profile just means the
defaults haven't been written yet, not that the caller asked for something invalid.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import events
from app.models.profile import ActivityLevel, BiologicalSex, GoalType, UserProfile, WeightUnit


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
    sex: BiologicalSex | None = None,
    age: int | None = None,
    height_in: Decimal | None = None,
    activity_level: ActivityLevel | None = None,
    goal_type: GoalType | None = None,
) -> UserProfile:
    profile = await get_or_create_profile(session, user_sub)
    if weight_unit is not None:
        profile.weight_unit = weight_unit
    if coach_notes is not None:
        profile.coach_notes = coach_notes.strip() or None
    if sex is not None:
        profile.sex = sex
    if age is not None:
        profile.age = age
    if height_in is not None:
        profile.height_in = height_in
    if activity_level is not None:
        profile.activity_level = activity_level
    if goal_type is not None:
        profile.goal_type = goal_type
    await session.flush()
    events.publish(user_sub, "profile")
    return profile


async def sync_display_name(session: AsyncSession, user_sub: str, display_name: str) -> None:
    """Called from `whoami` on every authenticated SPA load (#5, Partner v1) — keeps
    the display-name cache fresh from the caller's own current JWT claims. Not routed
    through `update_profile`/`events.publish`: this isn't a user-initiated settings
    change, just incidental upkeep, and firing a profile-changed event on every page
    load would spam the SSE listeners for nothing."""
    profile = await get_or_create_profile(session, user_sub)
    if profile.display_name != display_name:
        profile.display_name = display_name
        await session.flush()


async def complete_onboarding(session: AsyncSession, user_sub: str) -> UserProfile:
    """Idempotent — set once, never re-triggered by calling this again."""
    profile = await get_or_create_profile(session, user_sub)
    if profile.onboarding_completed_at is None:
        profile.onboarding_completed_at = datetime.now(UTC)
        await session.flush()
        events.publish(user_sub, "profile")
    return profile
