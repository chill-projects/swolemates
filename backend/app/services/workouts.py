"""Workouts service — exercises/workouts/workout_exercises/workout_sets (#3, resolved
— slice 1 of 5: core domain model + one-shot logging).
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import events
from app.models.workouts import Exercise, SetType, Workout, WorkoutExercise, WorkoutSet, WorkoutType


async def list_exercises(session: AsyncSession, user_sub: str) -> list[Exercise]:
    """Catalog + this user's own custom exercises (port of the legacy RLS policy:
    `is_custom = false OR created_by = user_sub`)."""
    result = await session.execute(
        select(Exercise)
        .where(Exercise.is_custom.is_(False) | (Exercise.created_by == user_sub))
        .order_by(Exercise.name)
    )
    return list(result.scalars())


async def _resolve_exercise(
    session: AsyncSession, user_sub: str, name: str, *, muscle_group: str | None = None
) -> Exercise:
    """Case-insensitive exact match against the catalog + this user's custom
    exercises; auto-creates a custom one if nothing matches. `log_workout` is
    conversational ("I did some cable pullovers"), so requiring a pre-existing
    catalog hit first would make anything off-catalog fail outright — a dedicated
    `search_exercises` tool for browsing the catalog is a later slice, not a
    prerequisite for logging.
    """
    normalized = name.strip()
    result = await session.execute(
        select(Exercise).where(
            func.lower(Exercise.name) == normalized.lower(),
            Exercise.is_custom.is_(False) | (Exercise.created_by == user_sub),
        )
    )
    exercise = result.scalar_one_or_none()
    if exercise is not None:
        return exercise

    exercise = Exercise(
        name=normalized, muscle_group=muscle_group or "other", is_custom=True, created_by=user_sub
    )
    session.add(exercise)
    await session.flush()
    return exercise


def _validate_sets(exercise_name: str, sets: list[dict]) -> None:
    """Port of docs/legacy/logic/workoutValidation.ts — same messages."""
    if not sets:
        raise ValueError(f"{exercise_name} needs at least one set.")
    for entry in sets:
        if entry.get("set_type", "reps") == "reps":
            reps = entry.get("reps")
            if reps is None or reps <= 0:
                raise ValueError(f"{exercise_name}: every rep set needs reps > 0.")
            weight = entry.get("weight")
            if weight is None or weight < 0:
                raise ValueError(
                    f"{exercise_name}: every rep set needs a weight (0 is fine for bodyweight)."
                )
        else:
            work_seconds = entry.get("work_seconds")
            if work_seconds is None or work_seconds <= 0:
                raise ValueError(f"{exercise_name}: every timed set needs work seconds > 0.")


@dataclass
class SetOut:
    id: uuid.UUID
    set_number: int
    set_type: SetType
    is_warmup: bool
    weight: Decimal | None
    reps: int | None
    work_seconds: int | None


@dataclass
class ExerciseEntryOut:
    id: uuid.UUID
    exercise_id: uuid.UUID
    exercise_name: str | None
    notes: str | None
    next_time_note: str | None
    sets: list[SetOut] = field(default_factory=list)


@dataclass
class WorkoutOut:
    id: uuid.UUID
    workout_type: WorkoutType
    activity_type: str | None
    duration_minutes: int | None
    title: str | None
    notes: str | None
    started_at: datetime
    completed_at: datetime | None
    exercises: list[ExerciseEntryOut] = field(default_factory=list)


async def _load_workout_details(
    session: AsyncSession, workout_ids: list[uuid.UUID]
) -> list[WorkoutOut]:
    if not workout_ids:
        return []
    result = await session.execute(
        select(Workout, WorkoutExercise, WorkoutSet, Exercise.name)
        .outerjoin(WorkoutExercise, WorkoutExercise.workout_id == Workout.id)
        .outerjoin(WorkoutSet, WorkoutSet.workout_exercise_id == WorkoutExercise.id)
        .outerjoin(Exercise, Exercise.id == WorkoutExercise.exercise_id)
        .where(Workout.id.in_(workout_ids))
        .order_by(WorkoutExercise.order_index, WorkoutSet.set_number)
    )

    workouts_by_id: dict[uuid.UUID, WorkoutOut] = {}
    entries_by_we_id: dict[uuid.UUID, ExerciseEntryOut] = {}
    for workout, we, ws, exercise_name in result.all():
        out = workouts_by_id.get(workout.id)
        if out is None:
            out = WorkoutOut(
                id=workout.id,
                workout_type=workout.workout_type,
                activity_type=workout.activity_type,
                duration_minutes=workout.duration_minutes,
                title=workout.title,
                notes=workout.notes,
                started_at=workout.started_at,
                completed_at=workout.completed_at,
            )
            workouts_by_id[workout.id] = out
        if we is None:
            continue
        entry = entries_by_we_id.get(we.id)
        if entry is None:
            entry = ExerciseEntryOut(
                id=we.id,
                exercise_id=we.exercise_id,
                exercise_name=exercise_name,
                notes=we.notes,
                next_time_note=we.next_time_note,
            )
            entries_by_we_id[we.id] = entry
            out.exercises.append(entry)
        if ws is not None:
            entry.sets.append(
                SetOut(
                    id=ws.id,
                    set_number=ws.set_number,
                    set_type=ws.set_type,
                    is_warmup=ws.is_warmup,
                    weight=ws.actual_weight,
                    reps=ws.actual_reps,
                    work_seconds=ws.work_seconds,
                )
            )

    return [workouts_by_id[wid] for wid in workout_ids if wid in workouts_by_id]


async def log_workout(
    session: AsyncSession,
    user_sub: str,
    *,
    exercises: list[dict],
    title: str | None = None,
    notes: str | None = None,
    logged_at: datetime | None = None,
) -> WorkoutOut:
    """One-shot: record an already-completed strength session in a single call (#3,
    resolved — this *is* legacy 0010's `save_strength_workout` RPC, now an ordinary
    service function doing the whole write in one transaction instead of plpgsql).

    `exercises`: [{"exercise": "Back Squat", "sets": [{"weight"?, "reps"?,
    "set_type"?, "work_seconds"?, "is_warmup"?}], "notes"?, "muscle_group"?}].
    Validated in full (workoutValidation.ts port) before anything is written.
    """
    if not exercises:
        raise ValueError("Add at least one exercise.")
    for entry in exercises:
        _validate_sets(entry["exercise"], entry.get("sets", []))

    when = logged_at or datetime.now(UTC)
    workout = Workout(
        user_id=user_sub,
        workout_type=WorkoutType.strength,
        title=title,
        notes=notes,
        started_at=when,
        completed_at=when,
    )
    session.add(workout)
    await session.flush()

    for order, entry in enumerate(exercises):
        exercise = await _resolve_exercise(
            session, user_sub, entry["exercise"], muscle_group=entry.get("muscle_group")
        )
        workout_exercise = WorkoutExercise(
            workout_id=workout.id,
            exercise_id=exercise.id,
            order_index=order,
            notes=entry.get("notes"),
            next_time_note=entry.get("next_time_note"),
        )
        session.add(workout_exercise)
        await session.flush()

        for set_number, set_entry in enumerate(entry["sets"], start=1):
            session.add(
                WorkoutSet(
                    workout_exercise_id=workout_exercise.id,
                    set_number=set_number,
                    set_type=SetType(set_entry.get("set_type", "reps")),
                    is_warmup=bool(set_entry.get("is_warmup", False)),
                    actual_weight=set_entry.get("weight"),
                    actual_reps=set_entry.get("reps"),
                    work_seconds=set_entry.get("work_seconds"),
                    completed_at=when,
                )
            )

    await session.flush()
    events.publish(user_sub, "workouts")
    details = await _load_workout_details(session, [workout.id])
    return details[0]


async def log_activity(
    session: AsyncSession,
    user_sub: str,
    *,
    activity_type: str,
    duration_minutes: int,
    title: str | None = None,
    notes: str | None = None,
    logged_at: datetime | None = None,
) -> WorkoutOut:
    """The simple legacy form — a non-strength session (yoga, a swim, a hike), no
    per-set detail."""
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be greater than 0.")

    when = logged_at or datetime.now(UTC)
    workout = Workout(
        user_id=user_sub,
        workout_type=WorkoutType.activity,
        activity_type=activity_type.strip(),
        duration_minutes=duration_minutes,
        title=title,
        notes=notes,
        started_at=when,
        completed_at=when,
    )
    session.add(workout)
    await session.flush()
    events.publish(user_sub, "workouts")
    details = await _load_workout_details(session, [workout.id])
    return details[0]


async def get_workout_history(
    session: AsyncSession,
    user_sub: str,
    *,
    start: date | None = None,
    end: date | None = None,
    exercise: str | None = None,
) -> list[WorkoutOut]:
    """Most-recent-first, optionally filtered to a date range and/or workouts that
    included a given exercise (by name, case-insensitive)."""
    conditions = [Workout.user_id == user_sub]
    if start is not None:
        conditions.append(Workout.started_at >= datetime.combine(start, time.min, tzinfo=UTC))
    if end is not None:
        conditions.append(Workout.started_at <= datetime.combine(end, time.max, tzinfo=UTC))
    if exercise is not None:
        matching = (
            select(WorkoutExercise.workout_id)
            .join(Exercise, Exercise.id == WorkoutExercise.exercise_id)
            .where(func.lower(Exercise.name) == exercise.strip().lower())
        )
        conditions.append(Workout.id.in_(matching))

    result = await session.execute(
        select(Workout.id).where(*conditions).order_by(Workout.started_at.desc())
    )
    workout_ids = [row[0] for row in result.all()]
    return await _load_workout_details(session, workout_ids)
