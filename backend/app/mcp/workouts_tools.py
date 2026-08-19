"""Workouts tools (#3, resolved). Slice 1: core domain model + one-shot logging.
Slice 2a: in-workout core (start/log_set/finish/get_active) — chat-usable per the #6
addendum ("bench 185x8" texted mid-workout). Slice 2b: bound to the
ui://swolemates/workout-live.html accordion (grouped by superset, last-time framing) —
any call that changes the active workout returns the full current picture, so the
component re-renders from any result without an extra round trip (the tmpx/nutrition-
day pattern). `update_workout_entry`/`list_workout_exercises` are app-only — driven by
the component's own buttons, no chat use case.
"""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastmcp.apps import AppConfig

from app.auth import mcp_user_sub
from app.mcp._adapter import catches_service_errors, tool_session
from app.mcp.server import mcp
from app.services import workouts as service

WORKOUT_LIVE_URI = "ui://swolemates/workout-live.html"

WORKOUT_LIVE_BUNDLE = (
    Path(__file__).resolve().parent.parent.parent / "static" / "mcp-apps" / "workout-live.html"
)


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
        base = f"{when} — {header}: {w.duration_minutes} min of {w.activity_type}"
    else:
        exercise_lines = "; ".join(
            f"{e.exercise_name}: " + ", ".join(_format_set(s) for s in e.sets) for e in w.exercises
        )
        base = f"{when} — {header}: {exercise_lines}"
    # So a later update_workout call has something to reference — text-only tools
    # (log_workout/log_activity/get_workout_history/update_workout itself) never
    # otherwise expose the id chat could target for a correction.
    extra = (
        f" (workout_id: {w.id})" + _format_celebrations(w.celebrations) + _format_streak(w.streak)
    )
    return base + extra


def _format_celebrations(celebrations: list[service.CelebrationOut]) -> str:
    if not celebrations:
        return ""
    parts = []
    for c in celebrations:
        label = "e1RM" if c.kind == "e1rm" else "weight"
        if c.previous is not None:
            parts.append(f"New PR: {c.exercise_name} {label} {c.value}lbs — up from {c.previous}")
        else:
            parts.append(f"New PR: {c.exercise_name} {label} {c.value}lbs")
    return " — " + "; ".join(parts)


def _format_streak(streak: service.StreakOut | None) -> str:
    if streak is None:
        return ""
    return f" — {streak.weeks}-week streak, {streak.this_week}/{streak.target} this week"


def _last_time_payload(lt: service.LastTimeOut | None) -> dict | None:
    if lt is None:
        return None
    return {
        "sets": [
            {"weight": float(s.weight) if s.weight is not None else None, "reps": s.reps}
            for s in lt.sets
        ],
        "note": lt.note,
    }


def _target_payload(t: service.TargetOut | None) -> dict | None:
    if t is None:
        return None
    return {
        "sets": t.sets,
        "reps": t.reps,
        "seconds": t.seconds,
        "weight": float(t.weight) if t.weight is not None else None,
    }


def _exercise_payload(e: service.ExerciseEntryOut) -> dict:
    return {
        "id": str(e.id),
        "exercise_id": str(e.exercise_id),
        "exercise_name": e.exercise_name,
        "next_time_note": e.next_time_note,
        "sets": [
            {
                "id": str(s.id),
                "set_number": s.set_number,
                "set_type": s.set_type.value,
                "is_warmup": s.is_warmup,
                "weight": float(s.weight) if s.weight is not None else None,
                "reps": s.reps,
                "work_seconds": s.work_seconds,
            }
            for s in e.sets
        ],
        "last_time": _last_time_payload(e.last_time),
        "target": _target_payload(e.target),
    }


def _celebration_payload(c: service.CelebrationOut) -> dict:
    return {
        "exercise_name": c.exercise_name,
        "kind": c.kind,
        "value": float(c.value),
        "previous": float(c.previous) if c.previous is not None else None,
    }


def _streak_payload(s: service.StreakOut | None) -> dict | None:
    if s is None:
        return None
    return {"weeks": s.weeks, "this_week": s.this_week, "target": s.target}


def _muscle_coverage_payload(coverage: list[service.MuscleCoverageOut]) -> list[dict]:
    """`get_workout_live` (app/services/workouts.py) already translates+collapses
    into body-highlighter slugs and fills in "none" for the full vocabulary — shared
    with the REST transport, which renders the same ui://workout-live.html component
    from the same service call. This is just JSON shaping."""
    return [{"muscle": c.muscle, "level": c.level} for c in coverage]


def _live_payload(live: service.WorkoutLiveOut) -> dict:
    return {
        "active": True,
        "id": str(live.id),
        "started_at": live.started_at.isoformat(),
        "completed_at": live.completed_at.isoformat() if live.completed_at else None,
        "notes": live.notes,
        "groups": [
            {
                "superset_group": g.superset_group,
                "is_superset": g.is_superset,
                "exercises": [_exercise_payload(e) for e in g.exercises],
            }
            for g in live.groups
        ],
        "summary": live.summary,
        "celebrations": [_celebration_payload(c) for c in live.celebrations],
        "streak": _streak_payload(live.streak),
        "muscle_coverage": _muscle_coverage_payload(live.muscle_coverage),
    }


@mcp.tool
@catches_service_errors
async def log_workout(
    exercises: list[dict], title: str | None = None, date: str | None = None
) -> str:
    """Record an already-completed strength workout in one call — the retroactive
    path ("I did 5x5 squats at 225lbs yesterday"), not the live in-gym flow. If this
    repeats a recent exercise or continues a streak, briefly compare it to last time
    and mention anything notable — a near-PR, a stalled lift, a broken or extended
    streak.

    Args:
        exercises: [{"exercise": "Back Squat", "sets": [{"weight": 225, "reps": 5}, ...],
            "notes"?, "next_time_note"?}, ...]. Each set: reps sets need "reps" > 0 and
            "weight" >= 0 (0 for bodyweight); timed sets need "set_type": "time" and
            "work_seconds" > 0. Add "is_warmup": true to exclude a set from PR checks.
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
async def update_workout(
    workout_id: str, exercise_updates: list[dict] | None = None, notes: str | None = None
) -> str:
    """Correct a past session conversationally — "actually that was 8 reps not
    6" — without needing to re-log anything. Not for adding a new exercise or
    set (log_workout covers backfilling a whole session); this only edits or
    removes what's already there. Recomputes any personal record this touches.

    Args:
        workout_id: from a prior log_workout/log_activity/get_workout_history/
            update_workout result's "(workout_id: ...)".
        exercise_updates: [{"exercise": "Back Squat" (must already be in this
            workout), "notes"?, "next_time_note"?, "sets"?: [{"set_number": 1
            (1-indexed, e.g. "the second set" = 2), "weight"?, "reps"?,
            "work_seconds"?, "is_warmup"?, "delete"?: true}]}]. Only the fields
            you pass on a set change; "delete" removes it entirely.
        notes: replaces the whole workout's own notes, if given.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        workout = await service.update_workout(
            session,
            user_sub,
            workout_id=UUID(workout_id),
            exercise_updates=exercise_updates,
            notes=notes,
        )
    return f"Updated: {_format_workout(workout)}"


@mcp.tool(app=AppConfig(resource_uri=WORKOUT_LIVE_URI, visibility=["model", "app"]))
@catches_service_errors
async def start_workout(
    exercises: list[str] | None = None,
    template_id: str | None = None,
    planned_id: str | None = None,
) -> dict:
    """Begin a workout session — from a blank slate, a known list of exercise names,
    a saved template, or a planned entry (plan_workout/get_planned_workouts). If
    one's already in progress, this just resumes it rather than starting a
    duplicate. planned_id takes precedence over template_id, which takes precedence
    over exercises, when more than one is given.

    Args:
        exercises: exercise names to start with, e.g. ["Back Squat", "Bench Press"].
            Ignored if template_id or planned_id is given.
        template_id: start from a saved template (from a prior
            create_workout_template/list_workout_templates result) — copies its
            exercises, superset grouping, and target sets/reps/weight in.
        planned_id: start from a scheduled entry (from a prior
            plan_workout/get_planned_workouts result) — uses its template and links
            the entry, so finishing this workout marks it done.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        workout = await service.start_workout(
            session,
            user_sub,
            exercises=exercises,
            template_id=UUID(template_id) if template_id else None,
            planned_id=UUID(planned_id) if planned_id else None,
        )
        live = await service.get_workout_live(session, user_sub, workout)
    return _live_payload(live)


@mcp.tool(app=AppConfig(resource_uri=WORKOUT_LIVE_URI, visibility=["model", "app"]))
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
) -> dict | str:
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
        is_warmup: excludes this set from PR checks.
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
        live = await service.get_workout_live(session, user_sub, result.workout)
    return _live_payload(live)


@mcp.tool(app=AppConfig(resource_uri=WORKOUT_LIVE_URI, visibility=["model", "app"]))
@catches_service_errors
async def finish_workout(workout_id: str, notes: str | None = None) -> dict:
    """Finish an in-progress workout — stamps it complete. If any exercise in it
    repeats a recent one or continues a streak, briefly compare it to last time and
    mention anything notable — a near-PR, a stalled lift, a broken or extended streak.

    Args:
        workout_id: from a prior start_workout/log_set/get_active_workout result.
        notes: optional freeform notes for the session.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        workout = await service.finish_workout(
            session, user_sub, workout_id=UUID(workout_id), notes=notes
        )
        live = await service.get_workout_live(session, user_sub, workout)
    return _live_payload(live)


@mcp.tool(app=AppConfig(resource_uri=WORKOUT_LIVE_URI, visibility=["app"]))
@catches_service_errors
async def get_active_workout() -> dict:
    """Check whether the caller has a workout currently in progress. App-only —
    driven by the component on load, not a chat entry point (start_workout/log_set
    already surface active-workout state when the model calls those)."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        workout = await service.get_active_workout(session, user_sub)
        if workout is None:
            return {"active": False, "summary": "No active workout."}
        live = await service.get_workout_live(session, user_sub, workout)
    return _live_payload(live)


@mcp.tool(app=AppConfig(resource_uri=WORKOUT_LIVE_URI, visibility=["app"]))
@catches_service_errors
async def update_workout_entry(
    workout_id: str,
    action: str,
    exercise: str | None = None,
    workout_exercise_id: str | None = None,
    superset_with: str | None = None,
    order: list[str] | None = None,
    note: str | None = None,
) -> dict:
    """App-only: add/remove/reorder an exercise mid-workout, or edit its
    next-time note. Driven by the component's own buttons.

    Args:
        workout_id: the in-progress workout being edited.
        action: "add_exercise" | "remove_exercise" | "reorder_exercises" |
            "set_next_time_note".
        exercise: for add_exercise — the exercise name.
        workout_exercise_id: for remove_exercise / set_next_time_note.
        superset_with: for add_exercise — an existing workout_exercise_id to
            group the new exercise with as a superset.
        order: for reorder_exercises — every current workout_exercise_id, in
            the new order.
        note: for set_next_time_note.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        workout = await service.update_workout_entry(
            session,
            user_sub,
            workout_id=UUID(workout_id),
            action=action,
            exercise=exercise,
            workout_exercise_id=UUID(workout_exercise_id) if workout_exercise_id else None,
            superset_with=UUID(superset_with) if superset_with else None,
            order=[UUID(i) for i in order] if order else None,
            note=note,
        )
        live = await service.get_workout_live(session, user_sub, workout)
    return _live_payload(live)


@mcp.tool(app=AppConfig(resource_uri=WORKOUT_LIVE_URI, visibility=["app"]))
@catches_service_errors
async def list_workout_exercises() -> dict:
    """App-only: the exercise catalog for the in-workout picker (filterable
    client-side — no chat search use case here)."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        exercises = await service.list_exercises(session, user_sub)
    return {
        "exercises": [
            {"id": str(e.id), "name": e.name, "muscle_group": e.muscle_group} for e in exercises
        ]
    }


@mcp.resource(WORKOUT_LIVE_URI)
def workout_live_ui() -> str:
    """The in-workout component — one bundle rendered by Claude and the SPA alike."""
    if WORKOUT_LIVE_BUNDLE.is_file():
        return WORKOUT_LIVE_BUNDLE.read_text()
    return (
        "<html><body style='font-family:system-ui;padding:1rem'>"
        "<p>The workout-live component bundle isn't built. Run <code>make apps</code>.</p>"
        "</body></html>"
    )
