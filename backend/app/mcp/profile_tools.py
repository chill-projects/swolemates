"""Profile tools — no `ui://` component. Onboarding's chat side is a genuine
conversation (#9), not a rendered widget, so these are plain text-returning tools.
"""

from contextlib import asynccontextmanager

from app.auth import mcp_user_sub
from app.db import get_sessionmaker
from app.mcp.server import mcp
from app.models.profile import ActivityLevel, BiologicalSex, GoalType, WeightUnit
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
    stats = (
        f"sex={profile.sex.value if profile.sex else 'unset'}, "
        f"age={profile.age or 'unset'}, "
        f"height_in={profile.height_in or 'unset'}, "
        f"activity_level={profile.activity_level.value if profile.activity_level else 'unset'}, "
        f"goal_type={profile.goal_type.value if profile.goal_type else 'unset'}"
    )
    return (
        f"Weight unit: {profile.weight_unit.value}. "
        f"Onboarding complete: {onboarded}. "
        f"Coach notes: {notes}. "
        f"TDEE inputs: {stats}."
    )


@mcp.tool
async def get_profile() -> str:
    """Read the caller's profile: weight-unit preference, coach notes, onboarding state."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        profile = await service.get_or_create_profile(session, user_sub)
        return _summary(profile)


@mcp.tool
async def update_profile(
    weight_unit: str | None = None,
    coach_notes: str | None = None,
    sex: str | None = None,
    age: int | None = None,
    height_in: float | None = None,
    activity_level: str | None = None,
    goal_type: str | None = None,
) -> str:
    """Update the caller's profile: weight-unit preference, coach notes, and/or the
    stats used to calculate nutrition targets (see calculate_targets).

    Args:
        weight_unit: "lbs" or "kg" — display preference only, storage stays canonical lbs.
        coach_notes: Freeform context for coaching (injuries, equipment limits, etc.) —
            replaces any existing notes; pass the full text, not a delta.
        sex: "male" or "female" — used only for the TDEE calculation.
        age: In years.
        height_in: Total height in inches (e.g. 5'2" = 62).
        activity_level: One of sedentary, light, moderate, active, very_active.
        goal_type: One of lose_weight, maintain, gain_muscle, recomp.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        profile = await service.update_profile(
            session,
            user_sub,
            weight_unit=WeightUnit(weight_unit) if weight_unit is not None else None,
            coach_notes=coach_notes,
            sex=BiologicalSex(sex) if sex is not None else None,
            age=age,
            height_in=height_in,
            activity_level=ActivityLevel(activity_level) if activity_level is not None else None,
            goal_type=GoalType(goal_type) if goal_type is not None else None,
        )
        return _summary(profile)


@mcp.tool
async def complete_onboarding() -> str:
    """Mark the caller's welcome/onboarding step as done, so it never shows again."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        profile = await service.complete_onboarding(session, user_sub)
        return _summary(profile)
