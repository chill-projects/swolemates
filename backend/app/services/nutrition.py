"""Nutrition service — logs/log_values/trackable_types/goals (#4, resolved)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import events
from app.models.nutrition import Goal, Log, LogValue, TrackableType


async def list_trackable_types(session: AsyncSession) -> list[TrackableType]:
    result = await session.execute(select(TrackableType).order_by(TrackableType.key))
    return list(result.scalars())


async def log_nutrition(
    session: AsyncSession,
    user_sub: str,
    *,
    entries: list[dict],
    logged_at: datetime | None = None,
    name: str | None = None,
    meal_type: str | None = None,
    source: str = "manual",
) -> Log:
    log = Log(
        user_id=user_sub,
        logged_at=logged_at or datetime.now(UTC),
        source=source,
        name=name,
        meal_type=meal_type,
        edited_by_user=False,
    )
    session.add(log)
    await session.flush()

    for entry in entries:
        session.add(
            LogValue(log_id=log.id, trackable_key=entry["trackable_key"], value=entry["value"])
        )
    await session.flush()
    events.publish(user_sub, "nutrition")
    return log


async def get_log_values(session: AsyncSession, user_sub: str, log_id: uuid.UUID) -> list[LogValue]:
    result = await session.execute(
        select(LogValue)
        .join(Log, Log.id == LogValue.log_id)
        .where(LogValue.log_id == log_id, Log.user_id == user_sub)
    )
    return list(result.scalars())


async def get_goals(session: AsyncSession, user_sub: str) -> list[Goal]:
    result = await session.execute(select(Goal).where(Goal.user_id == user_sub))
    return list(result.scalars())


async def set_goals(session: AsyncSession, user_sub: str, *, goals: list[dict]) -> list[Goal]:
    """Upserts each entry by (user_sub, trackable_key). At most one goal can carry
    is_streak_target — setting one clears it from every other goal of this user's
    first, service-side (not a DB constraint — #6, resolved)."""
    if any(g.get("is_streak_target") for g in goals):
        await session.execute(
            update(Goal).where(Goal.user_id == user_sub).values(is_streak_target=False)
        )

    existing = {g.trackable_key: g for g in await get_goals(session, user_sub)}
    for entry in goals:
        goal = existing.get(entry["trackable_key"])
        if goal is None:
            goal = Goal(user_id=user_sub, trackable_key=entry["trackable_key"], target_value=0)
            session.add(goal)
        goal.target_value = entry["target_value"]
        if "is_streak_target" in entry:
            goal.is_streak_target = entry["is_streak_target"]

    await session.flush()
    events.publish(user_sub, "nutrition")
    return await get_goals(session, user_sub)
