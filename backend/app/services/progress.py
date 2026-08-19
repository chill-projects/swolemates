"""The coach's trends dashboard (coach-prompt slice, resolved) — `get_progress`
composes existing streak/frequency/PR/nutrition-streak service functions into one
call, per `docs/proposals/claude-tools-v1.md` §3.5. Standalone module, like
`celebrations.py`: imports from `workouts.py`/`celebrations.py`/`nutrition.day`,
none of which import back.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workouts import SetType
from app.services.celebrations import FrequencyOut, StreakOut, get_streak, get_workout_frequency
from app.services.workouts import (
    PersonalRecordSummary,
    get_workout_history,
    list_personal_records,
)

Period = Literal["week", "month", "quarter"]
Focus = Literal["workouts", "nutrition", "all"]

_WINDOW_DAYS: dict[Period, int] = {"week": 7, "month": 30, "quarter": 90}


@dataclass
class LiftTrend:
    exercise_name: str
    direction: Literal["rising", "flat", "falling"]
    latest_weight: Decimal
    previous_weight: Decimal


@dataclass
class WorkoutProgress:
    streak: StreakOut
    frequency: FrequencyOut
    recent_prs: list[PersonalRecordSummary] = field(default_factory=list)
    trends: list[LiftTrend] = field(default_factory=list)


def _heaviest_set_weight(sets: list) -> Decimal | None:
    """The heaviest non-warmup, reps-type set in a session — the same PR-eligible
    filter `check_and_record_prs` uses, since a warmup or timed set carries no
    progressive-overload signal."""
    weights = [
        s.weight
        for s in sets
        if not s.is_warmup and s.set_type == SetType.reps and s.weight is not None
    ]
    return max(weights) if weights else None


def _compute_trends(history: list) -> list[LiftTrend]:
    """One entry per exercise with 2+ qualifying sessions in the window, comparing
    the two most recent. `history` is most-recent-first (get_workout_history's
    order), so sessions-per-exercise built by iterating it are already in that
    order."""
    sessions_by_exercise: dict[str, list[Decimal]] = {}
    for workout in history:
        for entry in workout.exercises:
            weight = _heaviest_set_weight(entry.sets)
            if weight is None or entry.exercise_name is None:
                continue
            sessions_by_exercise.setdefault(entry.exercise_name, []).append(weight)

    trends: list[LiftTrend] = []
    for exercise_name, weights in sessions_by_exercise.items():
        if len(weights) < 2:
            continue
        latest, previous = weights[0], weights[1]
        if latest > previous:
            direction = "rising"
        elif latest < previous:
            direction = "falling"
        else:
            direction = "flat"
        trends.append(
            LiftTrend(
                exercise_name=exercise_name,
                direction=direction,
                latest_weight=latest,
                previous_weight=previous,
            )
        )
    return trends


@dataclass
class NutritionProgress:
    streak: int
    adherence_pct: float | None = None
    hit_days: int = 0
    total_days: int = 0


@dataclass
class ProgressOut:
    period: str
    focus: str
    workouts: WorkoutProgress | None = None
    nutrition: NutritionProgress | None = None


async def get_progress(
    session: AsyncSession,
    user_sub: str,
    *,
    period: Period = "month",
    focus: Focus = "all",
    as_of: date | None = None,
) -> ProgressOut:
    if period not in _WINDOW_DAYS:
        raise ValueError(f"period must be one of week/month/quarter, got {period!r}")
    if focus not in ("workouts", "nutrition", "all"):
        raise ValueError(f"focus must be one of workouts/nutrition/all, got {focus!r}")

    # UTC, not date.today(): nutrition (log_nutrition/get_nutrition_streak/
    # get_nutrition_calendar) bounds every day in UTC with no per-user timezone yet
    # (nutrition/day.py), so a local `as_of` can disagree with a just-logged entry's
    # UTC date whenever local time and UTC fall on different calendar days.
    as_of = as_of or datetime.now(UTC).date()
    window_start = as_of - timedelta(days=_WINDOW_DAYS[period])

    workouts = None
    if focus in ("workouts", "all"):
        prs = await list_personal_records(session, user_sub)
        history = await get_workout_history(session, user_sub, start=window_start, end=as_of)
        workouts = WorkoutProgress(
            streak=await get_streak(session, user_sub, as_of=as_of),
            frequency=await get_workout_frequency(session, user_sub, as_of=as_of),
            recent_prs=[pr for pr in prs if window_start <= pr.achieved_at.date() <= as_of],
            trends=_compute_trends(history),
        )

    nutrition = None
    if focus in ("nutrition", "all"):
        from app.services.nutrition.day import get_nutrition_calendar, get_nutrition_streak
        from app.services.nutrition.goals import get_goals

        streak = await get_nutrition_streak(session, user_sub, as_of=as_of)
        goals = await get_goals(session, user_sub)
        has_calorie_goal = any(g.trackable_key == "calories" for g in goals)

        adherence_pct = None
        hit_days = 0
        total_days = 0
        if has_calorie_goal:
            calendar = await get_nutrition_calendar(
                session, user_sub, start=window_start, end=as_of
            )
            # `_day_status` reports "hit" unconditionally when no target is set, so a
            # day with no calorie goal would falsely count as adherence — the
            # has_calorie_goal guard above keeps that edge case from reaching here.
            counted = [d for d in calendar if d.status in ("hit", "miss")]
            hit_days = sum(1 for d in counted if d.status == "hit")
            total_days = len(counted)
            if total_days > 0:
                adherence_pct = round(hit_days / total_days * 100, 1)

        nutrition = NutritionProgress(
            streak=streak,
            adherence_pct=adherence_pct,
            hit_days=hit_days,
            total_days=total_days,
        )

    return ProgressOut(period=period, focus=focus, workouts=workouts, nutrition=nutrition)
