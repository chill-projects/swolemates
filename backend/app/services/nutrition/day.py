"""The day-vs-goals aggregate view (#4, resolved) — depends on trackables, goals, and
meal templates; nothing else in the nutrition package depends on this module.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.nutrition import Log, LogValue
from app.models.profile import GoalType
from app.services import profile as profile_service
from app.services.nutrition.goals import get_goals
from app.services.nutrition.templates import MealTemplateSummary, list_meal_templates
from app.services.nutrition.trackables import list_trackable_types

DayStatus = Literal["hit", "miss", "no-data"]

# Sanity bound on the backward walk in get_nutrition_streak, mirroring
# celebrations.py's MAX_STREAK_WEEKS_LOOKBACK — not a real limit anyone should hit.
MAX_NUTRITION_STREAK_LOOKBACK_DAYS = 365


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


@dataclass
class NutritionCalendarDay:
    date: date
    status: DayStatus
    hero: TrackableProgress
    bars: list[TrackableProgress]


def _goal_direction(goal_type: GoalType | None) -> Literal["deficit", "surplus", "maintain"] | None:
    """Direct port of `goalDirection()` in docs/legacy/logic/tdee.ts — never re-encoded
    as its own stored field, derived fresh each time from the same calorie multiplier
    `calculate_targets` uses (deferred import: `tdee` imports this package at call
    time, so importing it back at module load would cycle)."""
    if goal_type is None:
        return None
    from app.services.tdee import GOAL_PARAMS

    calorie_multiplier, _ = GOAL_PARAMS[goal_type]
    if calorie_multiplier < 1:
        return "deficit"
    if calorie_multiplier > 1:
        return "surplus"
    return "maintain"


def _day_status(
    *,
    has_logs: bool,
    consumed: Decimal,
    target: Decimal | None,
    direction: Literal["deficit", "surplus", "maintain"] | None,
) -> DayStatus:
    """Direct port of `dayStatus()` in docs/legacy/logic/tdee.ts. Grace windows are
    direction-aware: a deficit goal never fails for eating *less*, a surplus goal
    never fails for eating *more* — only "maintain" (or an unknown direction) uses a
    symmetric +/-10% band."""
    if not has_logs:
        return "no-data"
    if target is None:
        return "hit"
    if direction == "deficit":
        return "hit" if consumed <= target * Decimal("1.05") else "miss"
    if direction == "surplus":
        return "hit" if consumed >= target * Decimal("0.95") else "miss"
    return "hit" if target * Decimal("0.9") <= consumed <= target * Decimal("1.1") else "miss"


async def get_nutrition_calendar(
    session: AsyncSession, user_sub: str, *, start: date, end: date
) -> list[NutritionCalendarDay]:
    """One entry per day in `[start, end]` inclusive — the dashboard's nutrition
    calendar. `status` mirrors legacy's `ConsistencyCalendar`, never ported until
    now; `hero`/`bars` are the same per-day shape `get_nutrition_day` returns, so a
    calendar cell's hover detail is exactly "what `get_nutrition_day` would show for
    that date." Goals/targets/goal-direction are read once for the whole range
    (matching legacy, which also had no historical-target tracking)."""
    start_dt = datetime.combine(start, time.min, tzinfo=UTC)
    end_dt = datetime.combine(end, time.max, tzinfo=UTC)

    result = await session.execute(
        select(Log, LogValue)
        .outerjoin(LogValue, LogValue.log_id == Log.id)
        .where(Log.user_id == user_sub, Log.logged_at >= start_dt, Log.logged_at <= end_dt)
    )

    logged_dates: set[date] = set()
    totals_by_date: dict[date, dict[str, Decimal]] = {}
    for log, value in result.all():
        d = log.logged_at.date()
        logged_dates.add(d)
        if value is not None:
            day_totals = totals_by_date.setdefault(d, {})
            day_totals[value.trackable_key] = (
                day_totals.get(value.trackable_key, Decimal(0)) + value.value
            )

    types_by_key = {t.key: t for t in await list_trackable_types(session)}
    goals_by_key = {g.trackable_key: g for g in await get_goals(session, user_sub)}
    profile = await profile_service.get_or_create_profile(session, user_sub)
    direction = _goal_direction(profile.goal_type)
    calories_target = goals_by_key["calories"].target_value if "calories" in goals_by_key else None

    days: list[NutritionCalendarDay] = []
    d = start
    while d <= end:
        totals = totals_by_date.get(d, {})
        consumed_calories = totals.get("calories", Decimal(0))
        hero = TrackableProgress(
            trackable_key="calories",
            label=types_by_key["calories"].label,
            unit=types_by_key["calories"].unit,
            consumed=consumed_calories,
            target=calories_target,
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
            if key != "calories" and t.goal_eligible and t.category == "nutrition"
        ]
        status = _day_status(
            has_logs=d in logged_dates,
            consumed=consumed_calories,
            target=calories_target,
            direction=direction,
        )
        days.append(NutritionCalendarDay(date=d, status=status, hero=hero, bars=bars))
        d += timedelta(days=1)

    return days


async def get_nutrition_streak(
    session: AsyncSession, user_sub: str, *, as_of: date | None = None
) -> int:
    """Consecutive *logged* days walking back from `as_of` (today by default) — the
    partner-summary nutrition streak. Matches legacy's `computeStreak()`: any status
    counts (logged, not hit), so a logged-but-missed day keeps the streak alive; only
    a day with zero logs breaks it. A single distinct-dates query over a bounded
    lookback window, not one query per day."""
    as_of = as_of or datetime.now(UTC).date()
    start_dt = datetime.combine(
        as_of - timedelta(days=MAX_NUTRITION_STREAK_LOOKBACK_DAYS), time.min, tzinfo=UTC
    )
    end_dt = datetime.combine(as_of, time.max, tzinfo=UTC)

    result = await session.execute(
        select(Log.logged_at).where(
            Log.user_id == user_sub, Log.logged_at >= start_dt, Log.logged_at <= end_dt
        )
    )
    logged_dates = {row[0].date() for row in result.all()}

    streak = 0
    d = as_of
    while d in logged_dates:
        streak += 1
        d -= timedelta(days=1)
    return streak
