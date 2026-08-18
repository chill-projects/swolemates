"""Workouts service — exercises/workouts/workout_exercises/workout_sets (#3, resolved
— slice 1 of 5: core domain model + one-shot logging).
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import events
from app.models.workouts import (
    Exercise,
    PersonalRecord,
    PersonalRecordKind,
    SetType,
    Workout,
    WorkoutExercise,
    WorkoutSet,
    WorkoutType,
)
from app.services.celebrations import (
    CelebrationOut,
    StreakOut,
    check_and_record_prs,
    get_streak,
    recompute_pr,
)
from app.services.errors import NotFoundError

# log_set auto-continues an open workout within this window of its last set with no
# question asked; past it, Claude asks rather than guesses (#3/#6, resolved).
CONTINUATION_WINDOW = timedelta(minutes=90)


async def list_exercises(session: AsyncSession, user_sub: str) -> list[Exercise]:
    """Catalog + this user's own custom exercises (port of the legacy RLS policy:
    `is_custom = false OR created_by = user_sub`)."""
    result = await session.execute(
        select(Exercise)
        .where(Exercise.is_custom.is_(False) | (Exercise.created_by == user_sub))
        .order_by(Exercise.name)
    )
    return list(result.scalars())


@dataclass
class PersonalRecordSummary:
    exercise_name: str
    kind: PersonalRecordKind
    value: Decimal
    achieved_at: datetime


async def list_personal_records(
    session: AsyncSession, user_sub: str
) -> list[PersonalRecordSummary]:
    """The current-record cache `PersonalRecord` holds, joined to the exercise name —
    nothing lists this today; `check_and_record_prs`/`recompute_pr` only ever touch
    one `(user_id, exercise_id, kind)` row at a time."""
    result = await session.execute(
        select(PersonalRecord, Exercise.name)
        .join(Exercise, Exercise.id == PersonalRecord.exercise_id)
        .where(PersonalRecord.user_id == user_sub)
        .order_by(Exercise.name, PersonalRecord.kind)
    )
    return [
        PersonalRecordSummary(
            exercise_name=name, kind=pr.kind, value=pr.value, achieved_at=pr.achieved_at
        )
        for pr, name in result.all()
    ]


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
class LastTimeSetOut:
    weight: Decimal | None
    reps: int | None


@dataclass
class LastTimeOut:
    sets: list[LastTimeSetOut]
    note: str | None


@dataclass
class TargetOut:
    """The uniform prescription copied from a `TemplateExercise` at
    `start_workout(template_id=...)` time. `None` on `ExerciseEntryOut` for ad-hoc
    exercises — there's nothing to prefill from."""

    sets: int
    reps: int | None
    seconds: int | None
    weight: Decimal | None


@dataclass
class ExerciseEntryOut:
    id: uuid.UUID
    exercise_id: uuid.UUID
    exercise_name: str | None
    notes: str | None
    next_time_note: str | None
    sets: list[SetOut] = field(default_factory=list)
    superset_group: int | None = None
    # Populated only by `get_workout_live` — cheap everywhere else that reuses
    # this dataclass (get_workout_history, log_workout, ...) since it'd otherwise
    # be an extra query per exercise on every past workout returned.
    last_time: LastTimeOut | None = None
    target: TargetOut | None = None


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
    # Set only by start_workout, when it found (and returned) an already-active
    # workout instead of creating one — distinct from "has exercises", which is
    # also true for a brand-new workout started with a given exercise list (a bug
    # caught live: the MCP tool originally guessed this from `bool(exercises)`).
    resumed: bool = False
    # Populated only where sets are actually written (log_set, log_workout) — real
    # time, with an accurate `previous` value at the moment it happens. Empty
    # everywhere else, including finish_workout: it never writes sets in this app's
    # architecture, so it has nothing new to check (#3/#6, resolved).
    celebrations: list[CelebrationOut] = field(default_factory=list)
    # Populated only where a workout just completed (finish_workout, log_activity,
    # log_workout) — streak only depends on completed_at. None everywhere else.
    streak: StreakOut | None = None


@dataclass
class LogSetResult:
    """`workout` is None exactly when `needs_clarification` is set — the >90-minute
    gap case, where nothing gets written until the caller says which workout they
    mean (#3/#6, resolved: Claude asks rather than guesses)."""

    workout: WorkoutOut | None
    needs_clarification: str | None = None


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
            target = (
                TargetOut(
                    sets=we.target_sets,
                    reps=we.target_reps,
                    seconds=we.target_seconds,
                    weight=we.target_weight,
                )
                if we.target_sets is not None
                else None
            )
            entry = ExerciseEntryOut(
                id=we.id,
                exercise_id=we.exercise_id,
                exercise_name=exercise_name,
                notes=we.notes,
                next_time_note=we.next_time_note,
                superset_group=we.superset_group,
                target=target,
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


async def _get_active_workout(session: AsyncSession, user_sub: str) -> Workout | None:
    """At most one in-progress (`completed_at IS NULL`) workout per user, enforced
    here and in `start_workout`/`log_set` rather than a DB constraint — `.limit(1)`
    ordered most-recent-first is a defensive fallback if that invariant is ever
    violated, not an expectation that it will be."""
    result = await session.execute(
        select(Workout)
        .where(Workout.user_id == user_sub, Workout.completed_at.is_(None))
        .order_by(Workout.started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _last_activity_at(session: AsyncSession, workout: Workout) -> datetime:
    """The most recent set logged in this workout, or its start time if none yet —
    what "90 minutes since you last did anything" actually measures against."""
    result = await session.execute(
        select(func.max(WorkoutSet.completed_at))
        .join(WorkoutExercise, WorkoutExercise.id == WorkoutSet.workout_exercise_id)
        .where(WorkoutExercise.workout_id == workout.id)
    )
    return result.scalar_one_or_none() or workout.started_at


async def _find_or_create_workout_exercise(
    session: AsyncSession,
    user_sub: str,
    workout: Workout,
    exercise_name: str,
    *,
    note: str | None = None,
) -> WorkoutExercise:
    resolved = await _resolve_exercise(session, user_sub, exercise_name)
    result = await session.execute(
        select(WorkoutExercise).where(
            WorkoutExercise.workout_id == workout.id, WorkoutExercise.exercise_id == resolved.id
        )
    )
    workout_exercise = result.scalar_one_or_none()
    if workout_exercise is None:
        count_result = await session.execute(
            select(func.count(WorkoutExercise.id)).where(WorkoutExercise.workout_id == workout.id)
        )
        workout_exercise = WorkoutExercise(
            workout_id=workout.id,
            exercise_id=resolved.id,
            order_index=count_result.scalar_one() or 0,
            notes=note,
        )
        session.add(workout_exercise)
        await session.flush()
    elif note is not None:
        workout_exercise.notes = note
    return workout_exercise


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

    new_sets_by_exercise: list[tuple[uuid.UUID, str, list[WorkoutSet]]] = []
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

        new_sets: list[WorkoutSet] = []
        for set_number, set_entry in enumerate(entry["sets"], start=1):
            new_set = WorkoutSet(
                workout_exercise_id=workout_exercise.id,
                set_number=set_number,
                set_type=SetType(set_entry.get("set_type", "reps")),
                is_warmup=bool(set_entry.get("is_warmup", False)),
                actual_weight=set_entry.get("weight"),
                actual_reps=set_entry.get("reps"),
                work_seconds=set_entry.get("work_seconds"),
                completed_at=when,
            )
            session.add(new_set)
            new_sets.append(new_set)
        new_sets_by_exercise.append((exercise.id, exercise.name, new_sets))

    await session.flush()

    celebrations: list[CelebrationOut] = []
    for exercise_id, exercise_name, new_sets in new_sets_by_exercise:
        celebrations += await check_and_record_prs(
            session, user_sub, exercise_id=exercise_id, exercise_name=exercise_name, sets=new_sets
        )

    events.publish(user_sub, "workouts")
    details = await _load_workout_details(session, [workout.id])
    details[0].celebrations = celebrations
    details[0].streak = await get_streak(session, user_sub, as_of=when.date())
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
    details[0].streak = await get_streak(session, user_sub, as_of=when.date())
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


async def start_workout(
    session: AsyncSession,
    user_sub: str,
    *,
    exercises: list[str] | None = None,
    template_id: uuid.UUID | None = None,
    planned_id: uuid.UUID | None = None,
) -> WorkoutOut:
    """Begin a workout session — from a blank slate, a known list of exercise names,
    a saved template, or a planned entry (`plan_workout`/`get_planned_workouts`).
    `planned_id` takes precedence over `template_id`, which takes precedence over
    `exercises`, when more than one is given. Either template path copies each
    exercise's order, superset grouping, and target prescription onto the new
    session's `workout_exercises`; editing the template afterward never rewrites
    this copy. Starting from a planned entry also links it — `finish_workout` marks
    it done once the session completes. At most one active workout per user: if
    one's already in progress, this just returns it rather than creating a
    duplicate — resumability is a server-side-state guarantee, not a per-call one
    (#3, resolved)."""
    active = await _get_active_workout(session, user_sub)
    if active is not None:
        details = await _load_workout_details(session, [active.id])
        details[0].resumed = True
        return details[0]

    # Deferred imports: workout_templates.py/planned_workouts.py both import from
    # this module at load time, so the reverse reference has to happen at call
    # time instead, to avoid a circular import.
    if planned_id is not None:
        from app.services import planned_workouts

        planned = await planned_workouts.get_planned_workout(session, user_sub, planned_id)
        template_id = planned.template_id

    workout = Workout(
        user_id=user_sub,
        workout_type=WorkoutType.strength,
        started_at=datetime.now(UTC),
        completed_at=None,
    )
    session.add(workout)
    await session.flush()

    if template_id is not None:
        from app.services import workout_templates

        template = await workout_templates.get_workout_template(session, user_sub, template_id)
        for te in template.exercises:
            session.add(
                WorkoutExercise(
                    workout_id=workout.id,
                    exercise_id=te.exercise_id,
                    order_index=te.order_index,
                    superset_group=te.superset_group,
                    target_sets=te.sets,
                    target_reps=te.reps,
                    target_seconds=te.seconds,
                    target_weight=te.weight,
                )
            )
    else:
        for order, name in enumerate(exercises or []):
            resolved = await _resolve_exercise(session, user_sub, name)
            session.add(
                WorkoutExercise(workout_id=workout.id, exercise_id=resolved.id, order_index=order)
            )

    await session.flush()

    if planned_id is not None:
        from app.services import planned_workouts

        await planned_workouts.link_workout(session, planned_id, workout.id)
        await session.flush()

    events.publish(user_sub, "workouts")
    details = await _load_workout_details(session, [workout.id])
    return details[0]


async def log_set(
    session: AsyncSession,
    user_sub: str,
    *,
    exercise: str,
    reps: int | None = None,
    weight: Decimal | None = None,
    set_type: str = "reps",
    work_seconds: int | None = None,
    is_warmup: bool = False,
    sets: int = 1,
    note: str | None = None,
    continue_session: bool | None = None,
) -> LogSetResult:
    """Record one or more sets (`sets` — "3 sets of squats at 185x5" — against the
    active workout, auto-starting one if none is active. An open workout auto-
    continues with no question asked if its last set was within
    `CONTINUATION_WINDOW`; past that, nothing is written and a clarifying message
    comes back instead, unless `continue_session` says explicitly which the caller
    means (#3/#6, resolved).
    """
    _validate_sets(
        exercise,
        [{"set_type": set_type, "reps": reps, "weight": weight, "work_seconds": work_seconds}]
        * sets,
    )

    active = await _get_active_workout(session, user_sub)
    if active is not None:
        last_activity = await _last_activity_at(session, active)
        gap = datetime.now(UTC) - last_activity
        if gap > CONTINUATION_WINDOW:
            if continue_session is None:
                hours = round(gap.total_seconds() / 3600, 1)
                return LogSetResult(
                    workout=None,
                    needs_clarification=(
                        f"You have a workout from {hours}h ago still open — continue that one, "
                        "or start fresh? (pass continue_session=true to continue it, "
                        "or continue_session=false to start a new one)"
                    ),
                )
            if continue_session is False:
                active.completed_at = last_activity
                await session.flush()
                events.publish(user_sub, "workouts")
                active = None

    if active is None:
        active = Workout(
            user_id=user_sub,
            workout_type=WorkoutType.strength,
            started_at=datetime.now(UTC),
            completed_at=None,
        )
        session.add(active)
        await session.flush()

    workout_exercise = await _find_or_create_workout_exercise(
        session, user_sub, active, exercise, note=note
    )

    count_result = await session.execute(
        select(func.count(WorkoutSet.id)).where(
            WorkoutSet.workout_exercise_id == workout_exercise.id
        )
    )
    next_set_number = (count_result.scalar_one() or 0) + 1

    when = datetime.now(UTC)
    new_sets: list[WorkoutSet] = []
    for i in range(sets):
        new_set = WorkoutSet(
            workout_exercise_id=workout_exercise.id,
            set_number=next_set_number + i,
            set_type=SetType(set_type),
            is_warmup=is_warmup,
            actual_weight=weight,
            actual_reps=reps,
            work_seconds=work_seconds,
            completed_at=when,
        )
        session.add(new_set)
        new_sets.append(new_set)

    await session.flush()
    celebrations = await check_and_record_prs(
        session,
        user_sub,
        exercise_id=workout_exercise.exercise_id,
        exercise_name=exercise,
        sets=new_sets,
    )
    events.publish(user_sub, "workouts")
    details = await _load_workout_details(session, [active.id])
    details[0].celebrations = celebrations
    return LogSetResult(workout=details[0])


async def finish_workout(
    session: AsyncSession, user_sub: str, *, workout_id: uuid.UUID, notes: str | None = None
) -> WorkoutOut:
    """Stamps `completed_at`, drops any never-logged sets (workoutValidation port:
    empty prescribed-but-unlogged sets are dropped, not errors — a no-op today
    since blank-start sessions never create unlogged sets, but ready for slice 3's
    template-prescribed ones). No PR/streak computation yet — that's slice 4,
    wrapping around this function without changing its signature. Finishing with
    zero logged sets is allowed; there's no separate "discard" tool in this slice.
    """
    result = await session.execute(
        select(Workout).where(Workout.id == workout_id, Workout.user_id == user_sub)
    )
    workout = result.scalar_one_or_none()
    if workout is None:
        raise NotFoundError(f"No workout {workout_id}")

    await session.execute(
        delete(WorkoutSet).where(
            WorkoutSet.completed_at.is_(None),
            WorkoutSet.workout_exercise_id.in_(
                select(WorkoutExercise.id).where(WorkoutExercise.workout_id == workout_id)
            ),
        )
    )

    workout.completed_at = datetime.now(UTC)
    if notes is not None:
        workout.notes = notes

    await session.flush()

    from app.services import planned_workouts

    await planned_workouts.mark_done_if_planned(session, workout.id)
    await session.flush()

    events.publish(user_sub, "workouts")
    details = await _load_workout_details(session, [workout.id])
    details[0].streak = await get_streak(session, user_sub, as_of=workout.completed_at.date())
    return details[0]


async def get_workout(session: AsyncSession, user_sub: str, workout_id: uuid.UUID) -> WorkoutOut:
    result = await session.execute(
        select(Workout).where(Workout.id == workout_id, Workout.user_id == user_sub)
    )
    workout = result.scalar_one_or_none()
    if workout is None:
        raise NotFoundError(f"No workout {workout_id}")
    details = await _load_workout_details(session, [workout.id])
    return details[0]


async def update_workout(
    session: AsyncSession,
    user_sub: str,
    *,
    workout_id: uuid.UUID,
    exercise_updates: list[dict] | None = None,
    notes: str | None = None,
) -> WorkoutOut:
    """Edit a past session's actuals conversationally ("actually that was 8 reps
    not 6") — no add-exercise, no add-set, this corrects what's there rather than
    re-logging (`log_workout` covers backfilling a whole session). Targets by
    exercise name + `set_number` (1-indexed, stable, how a human would say "the
    second set of squats") rather than raw ids, which chat has no way to have
    seen. Recomputes any `personal_records` this touches — an edit or delete can
    just as easily unseat a cached record as set a new one.

    `exercise_updates`: [{"exercise": str, "notes"?, "next_time_note"?, "sets"?:
    [{"set_number": int, "weight"?, "reps"?, "work_seconds"?, "is_warmup"?,
    "delete"?: bool}]}]. Only passed fields change.
    """
    result = await session.execute(
        select(Workout).where(Workout.id == workout_id, Workout.user_id == user_sub)
    )
    workout = result.scalar_one_or_none()
    if workout is None:
        raise NotFoundError(f"No workout {workout_id}")

    if notes is not None:
        workout.notes = notes

    touched_exercise_ids: set[uuid.UUID] = set()
    for entry in exercise_updates or []:
        exercise_name = entry["exercise"]
        we_result = await session.execute(
            select(WorkoutExercise, Exercise.id)
            .join(Exercise, Exercise.id == WorkoutExercise.exercise_id)
            .where(
                WorkoutExercise.workout_id == workout.id,
                func.lower(Exercise.name) == exercise_name.strip().lower(),
            )
        )
        row = we_result.first()
        if row is None:
            raise ValueError(f"This workout has no {exercise_name!r}.")
        workout_exercise, exercise_id = row

        if "notes" in entry:
            workout_exercise.notes = entry["notes"]
        if "next_time_note" in entry:
            workout_exercise.next_time_note = entry["next_time_note"]

        for set_update in entry.get("sets", []):
            set_number = set_update["set_number"]
            set_result = await session.execute(
                select(WorkoutSet).where(
                    WorkoutSet.workout_exercise_id == workout_exercise.id,
                    WorkoutSet.set_number == set_number,
                )
            )
            workout_set = set_result.scalar_one_or_none()
            if workout_set is None:
                raise ValueError(f"{exercise_name} has no set {set_number}.")

            if set_update.get("delete"):
                await session.execute(delete(WorkoutSet).where(WorkoutSet.id == workout_set.id))
                touched_exercise_ids.add(exercise_id)
                continue

            if "weight" in set_update:
                workout_set.actual_weight = set_update["weight"]
            if "reps" in set_update:
                workout_set.actual_reps = set_update["reps"]
            if "work_seconds" in set_update:
                workout_set.work_seconds = set_update["work_seconds"]
            if "is_warmup" in set_update:
                workout_set.is_warmup = set_update["is_warmup"]
            touched_exercise_ids.add(exercise_id)

    await session.flush()

    for exercise_id in touched_exercise_ids:
        await recompute_pr(
            session, user_sub, exercise_id=exercise_id, kind=PersonalRecordKind.weight
        )
        await recompute_pr(session, user_sub, exercise_id=exercise_id, kind=PersonalRecordKind.e1rm)

    events.publish(user_sub, "workouts")
    details = await _load_workout_details(session, [workout.id])
    return details[0]


async def get_active_workout(session: AsyncSession, user_sub: str) -> WorkoutOut | None:
    active = await _get_active_workout(session, user_sub)
    if active is None:
        return None
    details = await _load_workout_details(session, [active.id])
    return details[0]


@dataclass
class GroupOut:
    superset_group: int | None
    is_superset: bool
    exercises: list[ExerciseEntryOut]


@dataclass
class WorkoutLiveOut:
    id: uuid.UUID
    started_at: datetime
    completed_at: datetime | None
    notes: str | None
    groups: list[GroupOut]
    summary: str
    celebrations: list[CelebrationOut] = field(default_factory=list)
    streak: StreakOut | None = None


async def _get_last_time(
    session: AsyncSession, user_sub: str, exercise_id: uuid.UUID, *, before_workout_id: uuid.UUID
) -> LastTimeOut | None:
    """The most recent *other*, *completed* workout that included this exercise —
    its sets plus whatever next-time note was left, for the progressive-overload
    framing ("Last time: 135lbs x 8, 8, 7"). `None` if this exercise has never
    been logged before."""
    result = await session.execute(
        select(WorkoutExercise.id, WorkoutExercise.next_time_note)
        .join(Workout, Workout.id == WorkoutExercise.workout_id)
        .where(
            Workout.user_id == user_sub,
            Workout.id != before_workout_id,
            Workout.completed_at.isnot(None),
            WorkoutExercise.exercise_id == exercise_id,
        )
        .order_by(Workout.completed_at.desc())
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None
    workout_exercise_id, note = row

    sets_result = await session.execute(
        select(WorkoutSet.actual_weight, WorkoutSet.actual_reps)
        .where(WorkoutSet.workout_exercise_id == workout_exercise_id)
        .order_by(WorkoutSet.set_number)
    )
    sets = [LastTimeSetOut(weight=w, reps=r) for w, r in sets_result.all()]
    return LastTimeOut(sets=sets, note=note)


def _group_exercises(exercises: list[ExerciseEntryOut]) -> list[GroupOut]:
    """The accordion unit is the group, not the exercise: null `superset_group` is
    a solo group of one (keyed by the entry's own id so nulls never merge); equal
    values form a superset. Dict insertion order preserves `_load_workout_details`'s
    order-by-`order_index` ordering, so groups display in first-appearance order
    with no separate ordering field needed."""
    buckets: dict[uuid.UUID | int, list[ExerciseEntryOut]] = {}
    for entry in exercises:
        key: uuid.UUID | int = (
            entry.superset_group if entry.superset_group is not None else entry.id
        )
        buckets.setdefault(key, []).append(entry)
    return [
        GroupOut(
            superset_group=key if isinstance(key, int) else None,
            is_superset=len(members) > 1,
            exercises=members,
        )
        for key, members in buckets.items()
    ]


def _live_summary(workout: WorkoutOut, groups: list[GroupOut]) -> str:
    total_sets = sum(len(e.sets) for g in groups for e in g.exercises)
    if workout.completed_at is not None:
        return f"Workout complete — {len(groups)} exercise group(s), {total_sets} sets logged."
    if not groups:
        return "No exercises yet."
    return f"{len(groups)} exercise group(s) so far, {total_sets} sets logged."


async def get_workout_live(
    session: AsyncSession, user_sub: str, workout: WorkoutOut
) -> WorkoutLiveOut:
    """The accordion view: `workout`'s exercises grouped by superset, each enriched
    with `last_time`. Takes an already-fetched `WorkoutOut` (every caller — start/
    log_set/finish/get_active — already has one) rather than reloading."""
    for entry in workout.exercises:
        entry.last_time = await _get_last_time(
            session, user_sub, entry.exercise_id, before_workout_id=workout.id
        )
    groups = _group_exercises(workout.exercises)
    return WorkoutLiveOut(
        id=workout.id,
        started_at=workout.started_at,
        completed_at=workout.completed_at,
        notes=workout.notes,
        groups=groups,
        summary=_live_summary(workout, groups),
        celebrations=workout.celebrations,
        streak=workout.streak,
    )


async def _next_superset_group(session: AsyncSession, workout_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.max(WorkoutExercise.superset_group)).where(
            WorkoutExercise.workout_id == workout_id
        )
    )
    return (result.scalar_one_or_none() or 0) + 1


async def _require_active_workout(
    session: AsyncSession, user_sub: str, workout_id: uuid.UUID
) -> Workout:
    result = await session.execute(
        select(Workout).where(Workout.id == workout_id, Workout.user_id == user_sub)
    )
    workout = result.scalar_one_or_none()
    if workout is None:
        raise NotFoundError(f"No workout {workout_id}")
    if workout.completed_at is not None:
        raise ValueError("This workout is already finished.")
    return workout


async def update_workout_entry(
    session: AsyncSession,
    user_sub: str,
    *,
    workout_id: uuid.UUID,
    action: str,
    exercise: str | None = None,
    workout_exercise_id: uuid.UUID | None = None,
    superset_with: uuid.UUID | None = None,
    order: list[uuid.UUID] | None = None,
    note: str | None = None,
) -> WorkoutOut:
    """App-only mutations for the in-workout component: add/remove/reorder an
    exercise mid-workout, or edit its next-time note. Editing an *already-logged*
    set is out of scope here (that's `update_workout`, slice 5) — `log_set` is the
    only way sets get written."""
    workout = await _require_active_workout(session, user_sub, workout_id)

    if action == "add_exercise":
        if exercise is None:
            raise ValueError("add_exercise needs 'exercise'.")
        resolved = await _resolve_exercise(session, user_sub, exercise)
        count_result = await session.execute(
            select(func.count(WorkoutExercise.id)).where(WorkoutExercise.workout_id == workout.id)
        )
        group = None
        if superset_with is not None:
            partner = await session.get(WorkoutExercise, superset_with)
            if partner is None or partner.workout_id != workout.id:
                raise NotFoundError("No such exercise in this workout.")
            if partner.superset_group is None:
                partner.superset_group = await _next_superset_group(session, workout.id)
            group = partner.superset_group
        session.add(
            WorkoutExercise(
                workout_id=workout.id,
                exercise_id=resolved.id,
                order_index=count_result.scalar_one() or 0,
                superset_group=group,
            )
        )
    elif action == "remove_exercise":
        if workout_exercise_id is None:
            raise ValueError("remove_exercise needs 'workout_exercise_id'.")
        we = await session.get(WorkoutExercise, workout_exercise_id)
        if we is None or we.workout_id != workout.id:
            raise NotFoundError("No such exercise in this workout.")
        set_count = await session.execute(
            select(func.count(WorkoutSet.id)).where(WorkoutSet.workout_exercise_id == we.id)
        )
        if set_count.scalar_one():
            raise ValueError("Can't remove an exercise that already has logged sets.")
        await session.execute(delete(WorkoutExercise).where(WorkoutExercise.id == we.id))
    elif action == "reorder_exercises":
        if not order:
            raise ValueError("reorder_exercises needs 'order'.")
        result = await session.execute(
            select(WorkoutExercise).where(WorkoutExercise.workout_id == workout.id)
        )
        existing = {we.id: we for we in result.scalars()}
        if set(order) != set(existing):
            raise ValueError("'order' must include exactly this workout's current exercises.")
        for index, we_id in enumerate(order):
            existing[we_id].order_index = index
    elif action == "set_next_time_note":
        if workout_exercise_id is None:
            raise ValueError("set_next_time_note needs 'workout_exercise_id'.")
        we = await session.get(WorkoutExercise, workout_exercise_id)
        if we is None or we.workout_id != workout.id:
            raise NotFoundError("No such exercise in this workout.")
        we.next_time_note = note
    else:
        raise ValueError(f"Unknown action: {action!r}")

    await session.flush()
    events.publish(user_sub, "workouts")
    details = await _load_workout_details(session, [workout.id])
    return details[0]
