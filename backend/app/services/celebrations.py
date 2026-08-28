"""Streaks + PR celebrations service (#3, resolved — slice 4).

No circular-import risk, unlike workout_templates.py/planned_workouts.py: this
module needs app.models.workouts (plain table defs, no service logic) plus its own
PersonalRecord, and app.services.profile (leaf: models + events only) for the
per-user timezone — workouts.py imports this module at module level, one direction.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workouts import (
    PersonalRecord,
    PersonalRecordKind,
    PlannedWorkout,
    SetType,
    Workout,
    WorkoutExercise,
    WorkoutSet,
)
from app.services import profile as profile_service
from app.services.timezones import local_day_bounds_utc, today_in

WEEK_TARGET_FALLBACK = 3
# A sanity bound on the backward walk in get_streak, not a real limit anyone should
# hit — guards against an unbounded loop, nothing more.
MAX_STREAK_WEEKS_LOOKBACK = 104


@dataclass
class CelebrationOut:
    exercise_name: str
    kind: str  # "weight" | "e1rm"
    value: Decimal
    previous: Decimal | None


@dataclass
class StreakOut:
    weeks: int
    this_week: int
    target: int


@dataclass
class FrequencyOut:
    workouts_last_7_days: int
    workouts_last_30_days: int
    total_workouts: int
    last_workout_at: datetime | None


def _week_bounds(d: date) -> tuple[date, date]:
    start = d - timedelta(days=d.weekday())
    return start, start + timedelta(days=6)


def _e1rm(weight: Decimal, reps: int) -> Decimal:
    return (weight * (1 + Decimal(reps) / Decimal(30))).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )


async def _maybe_upsert_pr(
    session: AsyncSession,
    user_sub: str,
    *,
    exercise_id: uuid.UUID,
    kind: PersonalRecordKind,
    value: Decimal,
    workout_set_id: uuid.UUID,
    achieved_at: datetime,
) -> tuple[Decimal, Decimal | None] | None:
    """Returns `(value, previous)` if this beat the cached record (or there wasn't
    one), else `None`. A tie doesn't count as a new record."""
    result = await session.execute(
        select(PersonalRecord).where(
            PersonalRecord.user_id == user_sub,
            PersonalRecord.exercise_id == exercise_id,
            PersonalRecord.kind == kind,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None and existing.value >= value:
        return None

    previous = existing.value if existing is not None else None
    if existing is None:
        session.add(
            PersonalRecord(
                user_id=user_sub,
                exercise_id=exercise_id,
                kind=kind,
                value=value,
                workout_set_id=workout_set_id,
                achieved_at=achieved_at,
            )
        )
    else:
        existing.value = value
        existing.workout_set_id = workout_set_id
        existing.achieved_at = achieved_at
    return value, previous


async def check_and_record_prs(
    session: AsyncSession,
    user_sub: str,
    *,
    exercise_id: uuid.UUID,
    exercise_name: str,
    sets: list[WorkoutSet],
) -> list[CelebrationOut]:
    """Checks heaviest-weight and best-e1RM (Epley: `w * (1 + reps/30)`) for each
    rep-based, non-warmup set with both weight and reps recorded. Timed and warmup
    sets are skipped entirely — no weight-PR concept applies to them."""
    celebrations: list[CelebrationOut] = []
    for s in sets:
        if s.is_warmup or s.set_type != SetType.reps:
            continue
        if s.actual_weight is None or s.actual_reps is None:
            continue

        weight_result = await _maybe_upsert_pr(
            session,
            user_sub,
            exercise_id=exercise_id,
            kind=PersonalRecordKind.weight,
            value=s.actual_weight,
            workout_set_id=s.id,
            achieved_at=s.completed_at,
        )
        if weight_result is not None:
            value, previous = weight_result
            celebrations.append(
                CelebrationOut(
                    exercise_name=exercise_name, kind="weight", value=value, previous=previous
                )
            )

        e1rm = _e1rm(s.actual_weight, s.actual_reps)
        e1rm_result = await _maybe_upsert_pr(
            session,
            user_sub,
            exercise_id=exercise_id,
            kind=PersonalRecordKind.e1rm,
            value=e1rm,
            workout_set_id=s.id,
            achieved_at=s.completed_at,
        )
        if e1rm_result is not None:
            value, previous = e1rm_result
            celebrations.append(
                CelebrationOut(
                    exercise_name=exercise_name, kind="e1rm", value=value, previous=previous
                )
            )

    if celebrations:
        await session.flush()
    return celebrations


async def _week_target(session: AsyncSession, user_sub: str, start: date, end: date) -> int:
    """The count of that week's `planned_workouts` rows (any status — rows are
    never deleted, per slice 3b), falling back to a flat 3 for a week with none."""
    result = await session.execute(
        select(func.count(PlannedWorkout.id)).where(
            PlannedWorkout.user_id == user_sub,
            PlannedWorkout.scheduled_for.between(start, end),
        )
    )
    count = result.scalar_one()
    return count if count > 0 else WEEK_TARGET_FALLBACK


async def _completed_count(
    session: AsyncSession, user_sub: str, start: date, end: date, tz: ZoneInfo
) -> int:
    """`start`/`end` are local calendar dates (inclusive); the window is their span in
    `tz`, converted to the UTC instants stored on the row."""
    start_dt, _ = local_day_bounds_utc(start, tz)
    _, end_dt = local_day_bounds_utc(end, tz)
    result = await session.execute(
        select(func.count(Workout.id)).where(
            Workout.user_id == user_sub,
            Workout.completed_at.isnot(None),
            Workout.completed_at >= start_dt,
            Workout.completed_at < end_dt,
        )
    )
    return result.scalar_one()


async def get_streak(
    session: AsyncSession, user_sub: str, *, as_of: date | None = None, tz: ZoneInfo | None = None
) -> StreakOut:
    """`this_week` counts completed workouts of any type (strength or activity) —
    "any day, any order, an unplanned bonus session counts too," per the resolved
    doc. `weeks` is the current run: the current week counts as a bonus if it's
    already hit target (even mid-week, since it isn't over yet), plus a backward
    walk through fully-elapsed prior weeks, stopping at the first that fell short
    of *its own* target.
    """
    tz = tz or await profile_service.get_user_timezone(session, user_sub)
    as_of = as_of or today_in(tz)
    this_start, this_end = _week_bounds(as_of)
    target = await _week_target(session, user_sub, this_start, this_end)
    this_week = await _completed_count(session, user_sub, this_start, this_end, tz)

    weeks = 1 if this_week >= target else 0
    week_start = this_start - timedelta(days=7)
    for _ in range(MAX_STREAK_WEEKS_LOOKBACK):
        week_end = week_start + timedelta(days=6)
        target_for_week = await _week_target(session, user_sub, week_start, week_end)
        completed = await _completed_count(session, user_sub, week_start, week_end, tz)
        if completed < target_for_week:
            break
        weeks += 1
        week_start -= timedelta(days=7)

    return StreakOut(weeks=weeks, this_week=this_week, target=target)


async def get_workout_frequency(
    session: AsyncSession, user_sub: str, *, as_of: date | None = None, tz: ZoneInfo | None = None
) -> FrequencyOut:
    """7/30-day counts, total, and last-workout date — the partner-summary stats,
    ported from legacy's `get_partner_workout_summary`. Reuses `_completed_count`
    windowed twice rather than a new query shape."""
    tz = tz or await profile_service.get_user_timezone(session, user_sub)
    as_of = as_of or today_in(tz)
    last_7 = await _completed_count(session, user_sub, as_of - timedelta(days=6), as_of, tz)
    last_30 = await _completed_count(session, user_sub, as_of - timedelta(days=29), as_of, tz)

    result = await session.execute(
        select(func.count(Workout.id), func.max(Workout.completed_at)).where(
            Workout.user_id == user_sub, Workout.completed_at.isnot(None)
        )
    )
    total, last_workout_at = result.one()

    return FrequencyOut(
        workouts_last_7_days=last_7,
        workouts_last_30_days=last_30,
        total_workouts=total,
        last_workout_at=last_workout_at,
    )


async def recompute_pr(
    session: AsyncSession, user_sub: str, *, exercise_id: uuid.UUID, kind: PersonalRecordKind
) -> None:
    """A full rescan, not the "does this beat the cached value" check
    `check_and_record_prs` does — for `update_workout` (slice 5), where an edit or
    delete can just as easily unseat the current record as set a new one. Deletes
    the cached row if nothing qualifies anymore, else points it at whichever set
    now genuinely holds the max."""
    result = await session.execute(
        select(WorkoutSet)
        .join(WorkoutExercise, WorkoutExercise.id == WorkoutSet.workout_exercise_id)
        .join(Workout, Workout.id == WorkoutExercise.workout_id)
        .where(
            Workout.user_id == user_sub,
            WorkoutExercise.exercise_id == exercise_id,
            WorkoutSet.is_warmup.is_(False),
            WorkoutSet.set_type == SetType.reps,
            WorkoutSet.actual_weight.isnot(None),
            WorkoutSet.actual_reps.isnot(None),
        )
    )
    sets = list(result.scalars())

    best_set: WorkoutSet | None = None
    best_value: Decimal | None = None
    for s in sets:
        value = (
            s.actual_weight
            if kind == PersonalRecordKind.weight
            else _e1rm(s.actual_weight, s.actual_reps)
        )
        if best_value is None or value > best_value:
            best_value = value
            best_set = s

    existing_result = await session.execute(
        select(PersonalRecord).where(
            PersonalRecord.user_id == user_sub,
            PersonalRecord.exercise_id == exercise_id,
            PersonalRecord.kind == kind,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if best_set is None or best_value is None:
        if existing is not None:
            await session.delete(existing)
        return

    if existing is None:
        session.add(
            PersonalRecord(
                user_id=user_sub,
                exercise_id=exercise_id,
                kind=kind,
                value=best_value,
                workout_set_id=best_set.id,
                achieved_at=best_set.completed_at,
            )
        )
    else:
        existing.value = best_value
        existing.workout_set_id = best_set.id
        existing.achieved_at = best_set.completed_at
