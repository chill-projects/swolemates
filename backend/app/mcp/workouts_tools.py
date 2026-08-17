"""Workouts tools (#3, resolved — slice 1 of 5: core domain model + one-shot
logging). Text-only for now — no ui:// component until slice 2 (in-workout mode).
"""

from contextlib import asynccontextmanager
from datetime import date, datetime

from app.auth import mcp_user_sub
from app.db import get_sessionmaker
from app.mcp.server import mcp
from app.services import workouts as service


@asynccontextmanager
async def tool_session():
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


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
        try:
            workout = await service.log_workout(
                session, user_sub, exercises=exercises, title=title, logged_at=when
            )
        except ValueError as exc:
            return str(exc)
    return f"Logged: {_format_workout(workout)}"


@mcp.tool
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
        try:
            workout = await service.log_activity(
                session,
                user_sub,
                activity_type=activity_type,
                duration_minutes=duration_minutes,
                title=title,
                notes=notes,
                logged_at=when,
            )
        except ValueError as exc:
            return str(exc)
    return f"Logged: {_format_workout(workout)}"


@mcp.tool
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
