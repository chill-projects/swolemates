"""Weekly pattern + planned workout tools (#3, resolved — slice 3b). set_weekly_
pattern/plan_workout/get_planned_workouts are chat-usable ("Monday is legs,
Tuesday is pool", "plan a leg day for Thursday", "what's coming up this week") and
bound to ui://swolemates/planned.html; update_planned_workout (skip/unskip) is
app-only, driven by the component's own buttons — matching update_workout_entry/
update_workout_template's precedent.

start_workout (already bound to workout-live's resource) is what the component's
own "Start" button calls, rather than a duplicate defined here — see workouts.py's
module docstring / the slice 3b plan for why that's a deliberate, stated trade-off
rather than a silent assumption.
"""

from datetime import date, timedelta
from pathlib import Path
from uuid import UUID

from fastmcp.apps import AppConfig

from app.auth import mcp_user_sub
from app.mcp._adapter import catches_service_errors, tool_session
from app.mcp._icons import app_icons
from app.mcp.server import mcp
from app.services import planned_workouts as service
from app.services import profile as profile_service
from app.services import workout_templates
from app.services.timezones import today_in

PLANNED_UI_URI = "ui://swolemates/planned.html"

PLANNED_UI_BUNDLE = (
    Path(__file__).resolve().parent.parent.parent / "static" / "mcp-apps" / "planned.html"
)


def _weekly_pattern_day_payload(d: service.WeeklyPatternDayOut) -> dict:
    return {
        "day_of_week": d.day_of_week,
        "template_id": str(d.template_id) if d.template_id else None,
        "template_name": d.template_name,
    }


def _planned_workout_payload(p: service.PlannedWorkoutOut) -> dict:
    return {
        "id": str(p.id),
        "template_id": str(p.template_id),
        "template_name": p.template_name,
        "scheduled_for": p.scheduled_for.isoformat(),
        "status": p.status.value,
        "workout_id": str(p.workout_id) if p.workout_id else None,
        "note": p.note,
        "exercise_names": p.exercise_names,
    }


@mcp.tool(app=AppConfig(resource_uri=PLANNED_UI_URI, visibility=["model", "app"]))
@catches_service_errors
async def get_weekly_pattern() -> dict:
    """Read the caller's current standing weekly split."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        pattern = await service.get_weekly_pattern(session, user_sub)
    return {"pattern": [_weekly_pattern_day_payload(d) for d in pattern]}


@mcp.tool(app=AppConfig(resource_uri=PLANNED_UI_URI, visibility=["model", "app"]))
@catches_service_errors
async def set_weekly_pattern(days: list[dict]) -> dict:
    """Set the caller's standing weekly split — "Monday is legs, Tuesday is pool" —
    replacing the whole week's pattern in one call. Only affects weeks generated
    after this call; already-scheduled dates don't retroactively change.

    Args:
        days: [{"day_of_week": 0-6 (0=Monday), "template_id"?: str}] — one entry
            per day you want scheduled; omit a day, or give it no template_id, for
            a rest day.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        parsed = [
            {
                "day_of_week": d["day_of_week"],
                "template_id": UUID(d["template_id"]) if d.get("template_id") else None,
            }
            for d in days
        ]
        pattern = await service.set_weekly_pattern(session, user_sub, days=parsed)
    return {"pattern": [_weekly_pattern_day_payload(d) for d in pattern]}


@mcp.tool(app=AppConfig(resource_uri=PLANNED_UI_URI, visibility=["model", "app"]))
@catches_service_errors
async def plan_workout(template_id: str, scheduled_for: str) -> dict:
    """Schedule one session on a specific date — including an extra one on an
    already-scheduled day.

    Args:
        template_id: from a prior create_workout_template/list_workout_templates result.
        scheduled_for: ISO date, e.g. "2026-08-20".
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        planned = await service.plan_workout(
            session,
            user_sub,
            template_id=UUID(template_id),
            scheduled_for=date.fromisoformat(scheduled_for),
        )
    return _planned_workout_payload(planned)


@mcp.tool(app=AppConfig(resource_uri=PLANNED_UI_URI, visibility=["model", "app"]))
@catches_service_errors
async def get_planned_workouts(start: str | None = None, end: str | None = None) -> dict:
    """What's coming up — generates any missing dates in range from the weekly
    pattern first, then returns the full list. Defaults to the next 7 days.

    Args:
        start: ISO date, inclusive. Defaults to today.
        end: ISO date, inclusive. Defaults to 6 days after start.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        if start:
            range_start = date.fromisoformat(start)
        else:
            tz = await profile_service.get_user_timezone(session, user_sub)
            range_start = today_in(tz)
        range_end = date.fromisoformat(end) if end else range_start + timedelta(days=6)
        planned = await service.get_planned_workouts(
            session, user_sub, start=range_start, end=range_end
        )
    return {"planned": [_planned_workout_payload(p) for p in planned]}


@mcp.tool(app=AppConfig(resource_uri=PLANNED_UI_URI, visibility=["app"]))
@catches_service_errors
async def update_planned_workout(planned_id: str, action: str) -> dict:
    """App-only: skip or unskip a scheduled entry. Driven by the component's buttons.

    Args:
        planned_id: the entry being edited.
        action: "skip" (only from a not-yet-started entry) | "unskip".
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        planned = await service.update_planned_workout(
            session, user_sub, planned_id=UUID(planned_id), action=action
        )
    return _planned_workout_payload(planned)


@mcp.tool(app=AppConfig(resource_uri=PLANNED_UI_URI, visibility=["app"]))
@catches_service_errors
async def list_templates_catalog() -> dict:
    """App-only: the caller's non-archived templates, for the pattern editor's
    per-day picker. Separate from templates_tools.list_workout_templates (plain
    text, for chat) — this returns structured data for the component."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        templates = await workout_templates.list_workout_templates(session, user_sub)
    return {"templates": [{"id": str(t.id), "name": t.name} for t in templates]}


@mcp.resource(PLANNED_UI_URI, icons=app_icons())
def planned_ui() -> str:
    """The planned-workouts component — one bundle rendered by Claude and the SPA alike."""
    if PLANNED_UI_BUNDLE.is_file():
        return PLANNED_UI_BUNDLE.read_text()
    return (
        "<html><body style='font-family:system-ui;padding:1rem'>"
        "<p>The planned-workouts component bundle isn't built. Run <code>make apps</code>.</p>"
        "</body></html>"
    )
