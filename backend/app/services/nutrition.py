"""Nutrition service — logs/log_values/trackable_types/goals (#4, resolved)."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal

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


@dataclass
class TrackableProgress:
    trackable_key: str
    label: str
    unit: str
    consumed: Decimal
    target: Decimal | None


@dataclass
class DayLog:
    id: uuid.UUID
    name: str | None
    logged_at: datetime
    meal_type: str | None
    values: dict[str, Decimal] = field(default_factory=dict)


@dataclass
class NutritionDay:
    date: date
    hero: TrackableProgress
    bars: list[TrackableProgress]
    streak_key: str | None
    logs: list[DayLog]


async def get_nutrition_day(
    session: AsyncSession, user_sub: str, day: date | None = None
) -> NutritionDay:
    """The day-vs-goals view (#4, resolved): the calorie ring is always the hero, and
    every other goal-eligible trackable with a target set renders as a bar — trackables
    logged without a goal (e.g. fat_g with no target) are summed into `logs` but don't
    get their own bar. Bounds the day in UTC; there's no per-user timezone yet.
    """
    day = day or datetime.now(UTC).date()
    start = datetime.combine(day, time.min, tzinfo=UTC)
    end = datetime.combine(day, time.max, tzinfo=UTC)

    result = await session.execute(
        select(Log, LogValue)
        .outerjoin(LogValue, LogValue.log_id == Log.id)
        .where(Log.user_id == user_sub, Log.logged_at >= start, Log.logged_at <= end)
        .order_by(Log.logged_at)
    )

    logs_by_id: dict[uuid.UUID, DayLog] = {}
    totals: dict[str, Decimal] = {}
    for log, value in result.all():
        day_log = logs_by_id.get(log.id)
        if day_log is None:
            day_log = DayLog(
                id=log.id, name=log.name, logged_at=log.logged_at, meal_type=log.meal_type
            )
            logs_by_id[log.id] = day_log
        if value is not None:
            day_log.values[value.trackable_key] = value.value
            totals[value.trackable_key] = totals.get(value.trackable_key, Decimal(0)) + value.value

    types_by_key = {t.key: t for t in await list_trackable_types(session)}
    goals_by_key = {g.trackable_key: g for g in await get_goals(session, user_sub)}
    streak_key = next((k for k, g in goals_by_key.items() if g.is_streak_target), None)

    calories = types_by_key["calories"]
    hero = TrackableProgress(
        trackable_key="calories",
        label=calories.label,
        unit=calories.unit,
        consumed=totals.get("calories", Decimal(0)),
        target=goals_by_key["calories"].target_value if "calories" in goals_by_key else None,
    )

    bars = [
        TrackableProgress(
            trackable_key=key,
            label=t.label,
            unit=t.unit,
            consumed=totals.get(key, Decimal(0)),
            target=goals_by_key[key].target_value,
        )
        for key, t in types_by_key.items()
        if key != "calories" and t.goal_eligible and key in goals_by_key
    ]

    return NutritionDay(
        date=day, hero=hero, bars=bars, streak_key=streak_key, logs=list(logs_by_id.values())
    )
