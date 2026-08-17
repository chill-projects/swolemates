"""Workouts tools (#3, resolved). Slice 1: core domain model + one-shot logging.
Slice 2a: in-workout core (start/log_set/finish/get_active) — chat-usable today
per the #6 addendum ("bench 185x8" texted mid-workout), but still text-only —
no ui:// component until slice 2b.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.auth import mcp_user_sub
from app.mcp._adapter import catches_service_errors, tool_session
from app.mcp.server import mcp
from app.services import workouts as service


def _format_set(s: service.SetOut) -> str:
    if s.set_type == service.SetType.time:
        base = f"{s.work_seconds}s"
    else:
        weight = f"{s.weight}lbs " if s.weight is not None else ""
        base = f"{weight}x{s.reps}"
    return f"{base} (warmup)" if s.is_warmup else base


def _format_workout(w: service.WorkoutOut) -> str:
    header = w.title or (w.activity_type or "Workout")
    when = w.started_at.date().isoformat()
    if w.workout_type == service.WorkoutType.activity:
        return f"{when} — {header}: {w.duration_minutes} min of {w.activity_type}"
    exercise_lines = "; ".join(
        f"{e.exercise_name}: " + ", ".join(_format_set(s) for s in e.sets) for e in w.exercises
    )
    return f"{when} — {header}: {exercise_lines}"


@mcp.tool
@catches_service_errors
async def log_workout(
    exercises: list[dict], title: str | None = None, date: str | None = None
) -> str:
    """Record an already-completed strength workout in one call — the retroactive
    path ("I did 5x5 squats at 225lbs yesterday"), not the live in-gym flow.

    Args:
        exercises: [{"exercise": "Back Squat", "sets": [{"weight": 225, "reps": 5}, ...],
            "notes"?, "next_time_note"?}, ...]. Each set: reps sets need "reps" > 0 and
            "weight" >= 0 (0 for bodyweight); timed sets need "set_type": "time" and
            "work_seconds" > 0. Add "is_warmup": true to exclude a set from PR checks
            (later slice).
        title: e.g. "Leg day".
        date: ISO date/datetime if backdating; defaults to now.
    """
    user_sub = mcp_user_sub()
    when = datetime.fromisoformat(date) if date else None
    async with tool_session() as session:
        workout = await service.log_workout(
            session, user_sub, exercises=exercises, title=title, logged_at=when
        )
    return f"Logged: {_format_workout(workout)}"


@mcp.tool
@catches_service_errors
async def log_activity(
    activity_type: str,
    duration_minutes: int,
    title: str | None = None,
    notes: str | None = None,
    date: str | None = None,
) -> str:
    """Log a non-strength session — yoga, a swim, a hike — the simple form, no
    per-set detail.

    Args:
        activity_type: free text, e.g. "yoga", "hot yoga", "pool".
        duration_minutes: how long, in minutes.
        title: optional label.
        notes: optional freeform notes.
        date: ISO date/datetime if backdating; defaults to now.
    """
    user_sub = mcp_user_sub()
    when = datetime.fromisoformat(date) if date else None
    async with tool_session() as session:
        workout = await service.log_activity(
            session,
            user_sub,
            activity_type=activity_type,
            duration_minutes=duration_minutes,
            title=title,
            notes=notes,
            logged_at=when,
        )
    return f"Logged: {_format_workout(workout)}"


@mcp.tool
@catches_service_errors
async def get_workout_history(
    start: str | None = None, end: str | None = None, exercise: str | None = None
) -> str:
    """Read past workouts, optionally filtered to a date range and/or workouts that
    included a given exercise.

    Args:
        start: ISO date, inclusive.
        end: ISO date, inclusive.
        exercise: exercise name (case-insensitive) — only workouts that included it.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        workouts = await service.get_workout_history(
            session,
            user_sub,
            start=date.fromisoformat(start) if start else None,
            end=date.fromisoformat(end) if end else None,
            exercise=exercise,
        )
    if not workouts:
        return "No workouts found."
    return "\n".join(_format_workout(w) for w in workouts)


@mcp.tool
@catches_service_errors
async def start_workout(exercises: list[str] | None = None) -> str:
    """Begin a workout session — from a blank slate or a known list of exercise
    names. If one's already in progress, this just resumes it rather than
    starting a duplicate (starting from a template/planned workout comes in a
    later slice, once those exist).

    Args:
        exercises: exercise names to start with, e.g. ["Back Squat", "Bench Press"].
            Optional — sets can be logged via log_set even without this.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        workout = await service.start_workout(session, user_sub, exercises=exercises)
    verb = "Resuming your open workout" if workout.resumed else "Started a new workout"
    return f"{verb}: {_format_workout(workout)}"


@mcp.tool
@catches_service_errors
async def log_set(
    exercise: str,
    reps: int | None = None,
    weight: Decimal | None = None,
    set_type: str = "reps",
    work_seconds: int | None = None,
    is_warmup: bool = False,
    sets: int = 1,
    note: str | None = None,
    continue_session: bool | None = None,
) -> str:
    """Record one or more sets against the active workout — auto-starts one if
    none is active. Auto-continues an already-open workout with no question
    asked if its last set was within 90 minutes; past that gap, nothing gets
    written and you'll get a clarifying question back instead, unless
    `continue_session` says explicitly which workout is meant.

    Args:
        exercise: e.g. "Back Squat".
        reps: for rep-based sets, > 0.
        weight: lbs, >= 0 (0 for bodyweight). Required for rep-based sets.
        set_type: "reps" (default) or "time".
        work_seconds: for timed sets, > 0.
        is_warmup: excludes this set from PR checks (later slice).
        sets: how many identical sets to log at once, e.g. 3 for "3 sets of squats
            at 185x5".
        note: freeform note for this exercise (e.g. "felt easy, add 5 next time").
        continue_session: only needed if you get a clarifying question back —
            true to continue the old open workout, false to start a fresh one.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        result = await service.log_set(
            session,
            user_sub,
            exercise=exercise,
            reps=reps,
            weight=weight,
            set_type=set_type,
            work_seconds=work_seconds,
            is_warmup=is_warmup,
            sets=sets,
            note=note,
            continue_session=continue_session,
        )
    if result.needs_clarification:
        return result.needs_clarification
    return f"Logged: {_format_workout(result.workout)}"


@mcp.tool
@catches_service_errors
async def finish_workout(workout_id: str, notes: str | None = None) -> str:
    """Finish an in-progress workout — stamps it complete.

    Args:
        workout_id: from a prior start_workout/log_set/get_active_workout result.
        notes: optional freeform notes for the session.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        workout = await service.finish_workout(
            session, user_sub, workout_id=UUID(workout_id), notes=notes
        )
    return f"Finished: {_format_workout(workout)}"


@mcp.tool
@catches_service_errors
async def get_active_workout() -> str:
    """Check whether the caller has a workout currently in progress."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        workout = await service.get_active_workout(session, user_sub)
    if workout is None:
        return "No active workout."
    return f"Active: {_format_workout(workout)}"
