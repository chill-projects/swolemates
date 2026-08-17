"""The day-vs-goals aggregate view (#4, resolved) — depends on trackables, goals, and
meal templates; nothing else in the nutrition package depends on this module.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.nutrition import Log, LogValue
from app.services.nutrition.goals import get_goals
from app.services.nutrition.templates import MealTemplateSummary, list_meal_templates
from app.services.nutrition.trackables import list_trackable_types


@dataclass
class TrackableProgress:
    trackable_key: str
    label: str
    unit: str
    consumed: Decimal
    target: Decimal | None


@dataclass
class DayLogItem:
    id: uuid.UUID
    name: str | None
    values: dict[str, Decimal]


@dataclass
class DayLog:
    """One line in the day's log. Ungrouped (the common case): `id` is the log's own
    id, `items` stays empty. Grouped (logged via a meal template): `id` is the shared
    group_id, `name` is the template's name snapshotted at log time, `values` are the
    combined totals across every item, and `items` holds the per-item breakdown (#4,
    resolved — "the logged-history entry also shows the per-item breakdown")."""

    id: uuid.UUID
    name: str | None
    logged_at: datetime
    meal_type: str | None
    values: dict[str, Decimal] = field(default_factory=dict)
    items: list[DayLogItem] = field(default_factory=list)


@dataclass
class NutritionDay:
    date: date
    hero: TrackableProgress
    bars: list[TrackableProgress]
    streak_key: str | None
    logs: list[DayLog]
    templates: list[MealTemplateSummary]


async def get_nutrition_day(
    session: AsyncSession, user_sub: str, day: date | None = None
) -> NutritionDay:
    """The day-vs-goals view (#4, resolved): the calorie ring is always the hero, and
    every other goal-eligible trackable always renders as a bar, whether or not a
    target's been set for it (matching the legacy TodaySummary.tsx reference this
    generalizes — `target` is just None until the caller sets one). Bounds the day in
    UTC; there's no per-user timezone yet.
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

    logs_by_id: dict[uuid.UUID, Log] = {}
    values_by_log: dict[uuid.UUID, dict[str, Decimal]] = {}
    log_order: list[uuid.UUID] = []
    totals: dict[str, Decimal] = {}
    for log, value in result.all():
        if log.id not in logs_by_id:
            logs_by_id[log.id] = log
            values_by_log[log.id] = {}
            log_order.append(log.id)
        if value is not None:
            values_by_log[log.id][value.trackable_key] = value.value
            totals[value.trackable_key] = totals.get(value.trackable_key, Decimal(0)) + value.value

    # Grouped by (group_id or the log's own id) so a template-logged meal collapses
    # into one DayLog with a per-item breakdown, while every other log — keyed
    # uniquely by its own id — passes through as a normal single-item entry.
    day_logs: dict[uuid.UUID, DayLog] = {}
    for log_id in log_order:
        log = logs_by_id[log_id]
        values = values_by_log[log_id]
        key = log.group_id or log.id
        entry = day_logs.get(key)
        if entry is None:
            entry = DayLog(
                id=key,
                name=log.group_name or log.name,
                logged_at=log.logged_at,
                meal_type=log.meal_type,
            )
            day_logs[key] = entry
        if log.group_id is not None:
            entry.items.append(DayLogItem(id=log.id, name=log.name, values=values))
        for trackable_key, v in values.items():
            entry.values[trackable_key] = entry.values.get(trackable_key, Decimal(0)) + v

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
            target=goals_by_key[key].target_value if key in goals_by_key else None,
        )
        for key, t in types_by_key.items()
        # category == "nutrition" excludes weight_lbs (#19, resolved): it's
        # goal-eligible so a target can be set, but its progress belongs in its own
        # progress-bar/graph framing, not mixed into the day's macro bars.
        if key != "calories" and t.goal_eligible and t.category == "nutrition"
    ]

    return NutritionDay(
        date=day,
        hero=hero,
        bars=bars,
        streak_key=streak_key,
        logs=list(day_logs.values()),
        templates=await list_meal_templates(session, user_sub),
    )
