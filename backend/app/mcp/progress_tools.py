"""Trends tools for the coach prompt (§3.5, resolved) — `get_progress` is the wide
observation tool (streaks, frequency, PRs, adherence, per-lift trends), `get_exercise_history`
is the deep one (a single exercise's recent sets + notes-for-next-time). Both text-only,
model food per the proposal ("deliberately no UI: this is model food") — no `ui://`
component, same shape as `get_goals`/`search_food_facts`.
"""

from app.auth import mcp_user_sub
from app.mcp._adapter import catches_service_errors, tool_session
from app.mcp.server import mcp
from app.services import progress as progress_service
from app.services import workouts as workouts_service
from app.services.progress import LiftTrend, NutritionProgress, ProgressOut, WorkoutProgress
from app.services.workouts import ExerciseHistoryOut


def _format_trend(t: LiftTrend) -> str:
    verb = {"rising": "up from", "falling": "down from", "flat": "flat at"}[t.direction]
    return f"{t.exercise_name}: {t.latest_weight}lb ({verb} {t.previous_weight}lb)"


def _format_workouts(w: WorkoutProgress) -> str:
    parts = [
        f"Streak: {w.streak.weeks} week(s) ({w.streak.this_week}/{w.streak.target} this week)",
        f"Frequency: {w.frequency.workouts_last_7_days} in the last 7 days, "
        f"{w.frequency.workouts_last_30_days} in the last 30",
    ]
    if w.recent_prs:
        prs = ", ".join(f"{pr.exercise_name} {pr.kind.value} {pr.value}" for pr in w.recent_prs)
        parts.append(f"Recent PRs: {prs}")
    if w.trends:
        parts.append("Trends: " + "; ".join(_format_trend(t) for t in w.trends))
    return "Workouts — " + ". ".join(parts) + "."


def _format_nutrition(n: NutritionProgress) -> str:
    text = f"Nutrition streak: {n.streak} day(s)"
    if n.adherence_pct is not None:
        text += f", adherence: {n.adherence_pct}% ({n.hit_days}/{n.total_days} days on target)"
    return text + "."


def _format_progress(p: ProgressOut) -> str:
    lines = [f"Progress ({p.period}, focus={p.focus}):"]
    if p.workouts is not None:
        lines.append(_format_workouts(p.workouts))
    if p.nutrition is not None:
        lines.append(_format_nutrition(p.nutrition))
    return "\n".join(lines)


def _format_history(h: ExerciseHistoryOut) -> str:
    if not h.sessions:
        return f"No history for {h.exercise_name} yet."
    lines = [f"{h.exercise_name} — {len(h.sessions)} recent session(s):"]
    for s in h.sessions:
        sets_text = ", ".join(
            f"{set_.weight}lb x{set_.reps}" if set_.reps is not None else f"{set_.work_seconds}s"
            for set_ in s.sets
        )
        line = f"- {s.date.date().isoformat()}: {sets_text}"
        if s.notes:
            line += f" ({s.notes})"
        lines.append(line)
    if h.latest_next_time_note:
        lines.append(f"Next time: {h.latest_next_time_note}")
    return "\n".join(lines)


@mcp.tool
@catches_service_errors
async def get_progress(period: str = "month", focus: str = "all") -> str:
    """The coaching dashboard: workout streak/frequency/PRs/lift trends and nutrition
    streak/goal adherence over a period. Call this before coaching — it's the "how are
    we doing?" view.

    Args:
        period: week/month/quarter (default month) — a rolling window ending today.
        focus: workouts/nutrition/all (default all).
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        progress = await progress_service.get_progress(
            session, user_sub, period=period, focus=focus
        )
    return _format_progress(progress)


@mcp.tool
@catches_service_errors
async def get_exercise_history(exercise: str, limit: int = 5) -> str:
    """Deep history for one exercise — recent sessions' sets and the notes-for-next-time
    left last time. The progressive-overload substrate: use this before suggesting a
    weight/rep change on a lift someone's about to repeat.

    Args:
        exercise: exercise name, e.g. "Barbell Back Squat".
        limit: how many recent sessions to include (default 5).
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        history = await workouts_service.get_exercise_history(
            session, user_sub, exercise=exercise, limit=limit
        )
    return _format_history(history)
