"""Nutrition goals (#4/#6/#19, resolved)."""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import events
from app.models.nutrition import Goal, TrackableType


async def get_goals(session: AsyncSession, user_sub: str) -> list[Goal]:
    result = await session.execute(select(Goal).where(Goal.user_id == user_sub))
    return list(result.scalars())


async def set_goals(session: AsyncSession, user_sub: str, *, goals: list[dict]) -> list[Goal]:
    """Upserts each entry by (user_sub, trackable_key). At most one goal can carry
    is_streak_target — setting one clears it from every other goal of this user's
    first, service-side (not a DB constraint — #6, resolved). Not every goal-eligible
    trackable can carry it, though: weight_lbs is goal-eligible but not
    streak-eligible (#19, resolved) — a flat or rising weigh-in during genuine
    recomposition isn't a "miss" the way a calorie overshoot is."""
    streak_keys = [g["trackable_key"] for g in goals if g.get("is_streak_target")]
    if streak_keys:
        result = await session.execute(
            select(TrackableType).where(TrackableType.key.in_(streak_keys))
        )
        types = {t.key: t for t in result.scalars()}
        ineligible = [k for k in streak_keys if types.get(k) and not types[k].streak_eligible]
        if ineligible:
            raise ValueError(f"{', '.join(ineligible)} can't be a streak target.")

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
        # `entry.get(...) is not None`, not `"is_streak_target" in entry`: the REST path
        # always sends the key (GoalIn.model_dump() includes unset fields as None), so
        # `in` can't distinguish "omitted" from "explicitly null" and was overwriting an
        # existing goal's flag with NULL — a constraint violation on UPDATE (INSERT
        # happened to survive via the column's Python-side default).
        if entry.get("is_streak_target") is not None:
            goal.is_streak_target = entry["is_streak_target"]

    await session.flush()
    events.publish(user_sub, "nutrition")
    return await get_goals(session, user_sub)
