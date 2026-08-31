"""Workout template tools (#3, resolved — slice 3a). create/get are chat-usable
("make me a pull day" -> create_workout_template) and bound to
ui://swolemates/template.html so Claude can render the result; update/archive/the
exercise-catalog lookup are app-only, driven by the component's own buttons — editing
happens in place, not conversationally (per the resolved doc's exact §8 split).
list_workout_templates stays plain text — it's a browsing tool, not the single-
template editor view, so it isn't bound to the component.
"""

from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastmcp.apps import AppConfig

from app.auth import mcp_user_sub
from app.mcp._adapter import catches_service_errors, tool_session
from app.mcp._icons import app_icons
from app.mcp.server import mcp
from app.services import workout_templates as service
from app.services import workouts as workouts_service

TEMPLATE_UI_URI = "ui://swolemates/template.html"

TEMPLATE_UI_BUNDLE = (
    Path(__file__).resolve().parent.parent.parent / "static" / "mcp-apps" / "template.html"
)


def _template_exercise_payload(e: service.TemplateExerciseOut) -> dict:
    return {
        "id": str(e.id),
        "exercise_id": str(e.exercise_id),
        "exercise_name": e.exercise_name,
        "superset_group": e.superset_group,
        "sets": e.sets,
        "reps": e.reps,
        "seconds": e.seconds,
        "weight": float(e.weight) if e.weight is not None else None,
        "notes": e.notes,
    }


def _template_payload(t: service.TemplateOut) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "description": t.description,
        "exercises": [_template_exercise_payload(e) for e in t.exercises],
    }


@mcp.tool(app=AppConfig(resource_uri=TEMPLATE_UI_URI, visibility=["model", "app"]))
@catches_service_errors
async def create_workout_template(name: str, exercises: list[dict]) -> dict:
    """Save a reusable prescription — "make me a pull day" — Claude picks the
    exercises and targets from the conversation, no template-builder wizard needed.

    Exercise names must match the catalog exactly (case-insensitive) to attach real
    muscle-group data — call search_exercises first ("squat" -> "Barbell Back Squat")
    rather than guessing a colloquial name; a near-miss silently creates a new custom
    exercise with no muscle map coverage on the workout view. If search_exercises
    finds nothing close, ask the user rather than guessing — see its docstring.

    Args:
        name: e.g. "Pull day".
        exercises: [{"exercise": "Deadlift", "sets": 3, "reps": 5, "weight"?: 225,
            "seconds"?: N (for timed exercises, instead of reps — exactly one of
            reps/seconds), "notes"?: str, "group"?: int, "muscle_group"?: str}].
            Give two or more entries the same "group" int to make them a superset.
            "muscle_group" only matters when this exercise doesn't already exist
            (exact match failed) — one of "legs", "arms", "shoulders", "back",
            "core", "chest"; ask the user which if they've chosen to add it as a
            new custom exercise, don't guess.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        template = await service.create_workout_template(
            session, user_sub, name=name, exercises=exercises
        )
    return _template_payload(template)


@mcp.tool(app=AppConfig(resource_uri=TEMPLATE_UI_URI, visibility=["model", "app"]))
@catches_service_errors
async def get_workout_template(template_id: str) -> dict:
    """Read one saved template's exercises and targets.

    Args:
        template_id: from a prior create_workout_template/list_workout_templates result.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        template = await service.get_workout_template(session, user_sub, UUID(template_id))
    return _template_payload(template)


@mcp.tool
@catches_service_errors
async def list_workout_templates() -> str:
    """List the caller's saved templates (excludes archived ones) — plain text, not
    the single-template editor (that's create_workout_template/get_workout_template,
    bound to the template component)."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        templates = await service.list_workout_templates(session, user_sub)
    if not templates:
        return "No saved templates yet."
    return "\n".join(
        f"{t.name} ({len(t.exercises)} exercise{'s' if len(t.exercises) != 1 else ''})"
        for t in templates
    )


@mcp.tool(app=AppConfig(resource_uri=TEMPLATE_UI_URI, visibility=["app"]))
@catches_service_errors
async def update_workout_template(
    template_id: str,
    action: str,
    name: str | None = None,
    exercise: str | None = None,
    template_exercise_id: str | None = None,
    superset_with: str | None = None,
    order: list[str] | None = None,
    sets: int | None = None,
    reps: int | None = None,
    seconds: int | None = None,
    weight: Decimal | None = None,
    notes: str | None = None,
) -> dict:
    """App-only: edit a template in place — rename, reorder, swap/add/remove an
    exercise, adjust sets/reps/weight, edit notes. Driven by the component's buttons.

    Args:
        template_id: the template being edited.
        action: "rename" | "add_exercise" | "remove_exercise" |
            "reorder_exercises" | "update_exercise".
        name: for rename.
        exercise: for add_exercise — the exercise name.
        template_exercise_id: for remove_exercise / update_exercise.
        superset_with: for add_exercise — an existing template_exercise_id to
            group the new exercise with as a superset.
        order: for reorder_exercises — every current template_exercise_id, in
            the new order.
        sets, reps, seconds, weight: for add_exercise (sets required, exactly
            one of reps/seconds) or update_exercise (only passed fields change).
        notes: for add_exercise / update_exercise.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        template = await service.update_workout_template(
            session,
            user_sub,
            template_id=UUID(template_id),
            action=action,
            name=name,
            exercise=exercise,
            template_exercise_id=UUID(template_exercise_id) if template_exercise_id else None,
            superset_with=UUID(superset_with) if superset_with else None,
            order=[UUID(i) for i in order] if order else None,
            sets=sets,
            reps=reps,
            seconds=seconds,
            weight=weight,
            notes=notes,
        )
    return _template_payload(template)


@mcp.tool(app=AppConfig(resource_uri=TEMPLATE_UI_URI, visibility=["app"]))
@catches_service_errors
async def archive_workout_template(template_id: str) -> str:
    """App-only: archive a template (soft-remove — hidden from listing, not deleted).

    Args:
        template_id: the template to archive.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        await service.archive_workout_template(session, user_sub, UUID(template_id))
    return "Archived."


@mcp.tool(app=AppConfig(resource_uri=TEMPLATE_UI_URI, visibility=["app"]))
@catches_service_errors
async def list_exercise_catalog() -> dict:
    """App-only: the exercise catalog for the template editor's picker (filterable
    client-side). Separate from workouts_tools.list_workout_exercises — tools bound
    to one ui:// resource aren't assumed callable from another's iframe."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        exercises = await workouts_service.list_exercises(session, user_sub)
    return {
        "exercises": [
            {
                "id": str(e.id),
                "name": e.name,
                "muscle_group": e.muscle_group,
                "equipment": e.equipment,
            }
            for e in exercises
        ]
    }


@mcp.resource(TEMPLATE_UI_URI, icons=app_icons())
def template_ui() -> str:
    """The template editor component — one bundle rendered by Claude and the SPA alike."""
    if TEMPLATE_UI_BUNDLE.is_file():
        return TEMPLATE_UI_BUNDLE.read_text()
    return (
        "<html><body style='font-family:system-ui;padding:1rem'>"
        "<p>The template component bundle isn't built. Run <code>make apps</code>.</p>"
        "</body></html>"
    )
