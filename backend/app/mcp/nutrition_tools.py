"""Nutrition tools (#4). log_nutrition and get_nutrition_day both render the day-vs-
goals view via ui://swolemates/nutrition-day.html — any call that changes today's
totals returns the full current picture, so the component re-renders from any result
without an extra round trip (the tmpx pattern). get_goals/set_goals stay text-only
permanently, per claude-tools-v1.md §3.4.
"""

from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastmcp.apps import AppConfig

from app.auth import mcp_user_sub
from app.mcp._adapter import catches_service_errors, tool_session
from app.mcp._icons import app_icons
from app.mcp._resources import NUTRITION_UI_URI
from app.mcp.server import mcp
from app.services import nutrition as service

NUTRITION_UI_BUNDLE = (
    Path(__file__).resolve().parent.parent.parent / "static" / "mcp-apps" / "nutrition-day.html"
)


def _progress(tp: service.TrackableProgress) -> dict:
    return {
        "trackable_key": tp.trackable_key,
        "label": tp.label,
        "unit": tp.unit,
        "consumed": float(tp.consumed),
        "target": float(tp.target) if tp.target is not None else None,
    }


def _summary(day: service.NutritionDay) -> str:
    """'1,430 kcal so far, 96 g protein — 64 g to go', where the 'to go' figure tracks
    whichever goal is the streak target (the metric that actually matters for the
    user's stated aim) rather than always defaulting to calories. `day.bars` always
    includes every goal-eligible macro now (so the UI can always show all 4), but the
    chat text only mentions ones that are actually logged or goaled — an untouched,
    goalless macro isn't worth a clause in the sentence.
    """
    parts = [f"{round(float(day.hero.consumed)):,} {day.hero.unit} so far"]
    mentionable = [b for b in day.bars if b.target is not None or b.consumed]
    parts += [f"{round(float(b.consumed))} {b.unit} {b.label.lower()}" for b in mentionable]
    text = ", ".join(parts)

    focus = (
        day.hero
        if day.streak_key in (None, "calories")
        else next((b for b in day.bars if b.trackable_key == day.streak_key), None)
    )
    if focus is not None and focus.target is not None:
        remaining = float(focus.target) - float(focus.consumed)
        if remaining >= 0:
            text += f" — {round(remaining):,} {focus.unit} to go"
        else:
            text += f" — {round(-remaining):,} {focus.unit} over"
    return text


def _template_payload(t: service.MealTemplateSummary) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "default_meal_type": t.default_meal_type,
        "items": [
            {
                "id": str(i.id),
                "name": i.name,
                "serving_description": i.serving_description,
                "values": {k: float(v) for k, v in i.values.items()},
            }
            for i in t.items
        ],
        "totals": {k: float(v) for k, v in t.totals.items()},
    }


async def _day_payload(session, user_sub: str) -> dict:
    day = await service.get_nutrition_day(session, user_sub)
    return {
        "date": day.date.isoformat(),
        "hero": _progress(day.hero),
        "bars": [_progress(b) for b in day.bars],
        "streak_key": day.streak_key,
        "logs": [
            {
                "id": str(log.id),
                "name": log.name,
                "logged_at": log.logged_at.isoformat(),
                "meal_type": log.meal_type,
                "values": {k: float(v) for k, v in log.values.items()},
                "items": [
                    {
                        "id": str(i.id),
                        "name": i.name,
                        "values": {k: float(v) for k, v in i.values.items()},
                    }
                    for i in log.items
                ],
            }
            for log in day.logs
        ],
        "templates": [_template_payload(t) for t in day.templates],
        "summary": _summary(day),
    }


async def _resolve_template_id(
    session, user_sub: str, *, template_id: str | None, name: str | None
) -> UUID:
    if template_id is not None:
        return UUID(template_id)
    if name is None:
        raise ValueError("Provide either template_id or name.")
    templates = await service.list_meal_templates(session, user_sub)
    match = next((t for t in templates if t.name.lower() == name.lower()), None)
    if match is None:
        raise service.NotFoundError(f"No meal template named {name!r}")
    return match.id


@mcp.tool(app=AppConfig(resource_uri=NUTRITION_UI_URI))
@catches_service_errors
async def get_nutrition_day() -> dict:
    """Show today's nutrition so far against the caller's goals."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        return await _day_payload(session, user_sub)


@mcp.tool(app=AppConfig(resource_uri=NUTRITION_UI_URI, visibility=["model", "app"]))
@catches_service_errors
async def log_nutrition(
    entries: list[dict], name: str | None = None, meal_type: str | None = None
) -> dict:
    """Record one or more trackable entries — a meal, a glass of water, creatine, today's
    body weight — in one call. Briefly compare today to last time if notable — how close
    today is to target, or that this extends/breaks a logging or goal-adherence streak —
    without making them ask.

    A meal with separately-adjustable components (a bowl with mix-ins, a plate with
    sides) needs one log_nutrition call per component, not one call combining
    everything — e.g. "yogurt bowl: yogurt, apple, chia seeds, granola" is 4 calls, not
    1. save_meal_template later snapshots whatever's already logged one-for-one, so a
    combined entry becomes a template with a single fixed-portion item nobody can
    adjust; separate entries become separately-adjustable items. A single genuinely
    indivisible dish ("chicken and rice") still gets one call.

    Args:
        entries: [{"trackable_key": "calories", "value": 450}, ...]. Valid keys today:
            calories, protein_g, carbs_g, fat_g, fiber_g, weight_lbs. If this food came
            from search_food_facts, include every non-null macro that match reported,
            not just calories/protein — the day view shows all of them. weight_lbs is
            always pounds regardless of the user's display unit preference — convert
            before calling if they gave you kg (lbs = kg * 2.20462) — and stands alone
            (its own entry, not mixed into a food entry's macros); it also unlocks
            calculate_targets, which needs a logged weight to run.
        name: What was logged, e.g. "chicken and rice". Use "Weight" for a weight-only entry.
        meal_type: breakfast/lunch/dinner/snack, if applicable — omit for a weight entry.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        await service.log_nutrition(
            session, user_sub, entries=entries, name=name, meal_type=meal_type, source="manual"
        )
        return await _day_payload(session, user_sub)


@mcp.tool
@catches_service_errors
async def update_nutrition_log(
    log_id: str,
    name: str | None = None,
    meal_type: str | None = None,
    values: dict[str, float] | None = None,
) -> str:
    """Edit a past nutrition entry conversationally — "actually that was a small
    coffee, not a large." Only the fields you pass change; `values` patches
    individual macros (e.g. just {"calories": 80}) rather than replacing the whole
    set, so you don't need to restate numbers that were already right.

    Args:
        log_id: the entry to edit (from a prior log_nutrition/get_nutrition_day result).
        name: new name, if it's changing.
        meal_type: new meal_type, if it's changing.
        values: trackable_key -> new value, for whichever macros were wrong.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        log = await service.update_nutrition_log(
            session,
            user_sub,
            log_id=UUID(log_id),
            name=name,
            meal_type=meal_type,
            values={k: Decimal(str(v)) for k, v in (values or {}).items()},
        )
        log_values = await service.get_log_values(session, user_sub, log.id)
    macros = ", ".join(f"{v.trackable_key}={v.value}" for v in log_values) or "no values"
    return f'Updated "{log.name or "entry"}" — {macros}.'


@mcp.tool
@catches_service_errors
async def amend_last_log(
    name: str | None = None,
    meal_type: str | None = None,
    values: dict[str, float] | None = None,
) -> str:
    """Undo or fix the single most recent nutrition entry, without needing its id —
    "undo that" or "actually that was 300 calories." Pass nothing to remove the entry
    outright; pass any field to correct it in place instead.

    Args:
        name: new name, if correcting (omit to leave alone, or to just undo).
        meal_type: new meal_type, if correcting.
        values: trackable_key -> new value, for whichever macros were wrong.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        updated, log_id, log_name = await service.amend_last_log(
            session,
            user_sub,
            name=name,
            meal_type=meal_type,
            values={k: Decimal(str(v)) for k, v in (values or {}).items()},
        )
        if updated is None:
            return f'Removed "{log_name or "that entry"}" from today\'s log.'
        log_values = await service.get_log_values(session, user_sub, log_id)
    macros = ", ".join(f"{v.trackable_key}={v.value}" for v in log_values) or "no values"
    return f'Updated "{updated.name or "entry"}" — {macros}.'


@mcp.tool(app=AppConfig(resource_uri=NUTRITION_UI_URI, visibility=["app"]))
@catches_service_errors
async def delete_nutrition_log(log_id: str) -> dict:
    """App-only: delete a logged entry outright — driven by the log list's own
    delete control (with its own confirm step), not a chat entry point. Kept off
    the model's tool list on purpose, same as delete_meal_template; for a chat-
    driven undo, amend_last_log (most-recent-only) is still the right tool.

    Args:
        log_id: the entry to delete (from a prior log_nutrition/get_nutrition_day result).
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        await service.delete_nutrition_log(session, user_sub, UUID(log_id))
        return await _day_payload(session, user_sub)


@mcp.tool(app=AppConfig(resource_uri=NUTRITION_UI_URI, visibility=["model", "app"]))
@catches_service_errors
async def save_meal_template(
    name: str,
    log_ids: list[str],
    default_meal_type: str | None = None,
    template_id: str | None = None,
) -> dict:
    """Save a recurring meal from things already logged today — save-from-log only,
    there's no from-scratch builder. Pass template_id to revise an existing template's
    items instead of creating a new one.

    Args:
        name: What to call it, e.g. "my usual breakfast".
        log_ids: ids of already-logged entries to bundle into this template (from a
            prior log_nutrition/get_nutrition_day result).
        default_meal_type: breakfast/lunch/dinner/snack, if this template usually goes
            under one.
        template_id: revise this existing template instead of creating a new one.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        await service.save_meal_template(
            session,
            user_sub,
            name=name,
            log_ids=[UUID(i) for i in log_ids],
            default_meal_type=default_meal_type,
            template_id=UUID(template_id) if template_id else None,
        )
        return await _day_payload(session, user_sub)


@mcp.tool(app=AppConfig(resource_uri=NUTRITION_UI_URI, visibility=["app"]))
@catches_service_errors
async def delete_meal_template(template_id: str) -> dict:
    """App-only: delete a saved meal template — driven by the template card's own
    delete control (with its own confirm step), not a chat entry point. Kept off the
    model's tool list on purpose so a casual mention in conversation ("get rid of
    that") can't delete something; matches archive_workout_template's precedent for
    the analogous workout-template action.

    Args:
        template_id: the template to delete.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        await service.delete_meal_template(session, user_sub, UUID(template_id))
        return await _day_payload(session, user_sub)


@mcp.tool(app=AppConfig(resource_uri=NUTRITION_UI_URI, visibility=["model", "app"]))
@catches_service_errors
async def update_meal_template_item(
    template_id: str,
    item_id: str,
    name: str,
    values: dict[str, float],
    serving_description: str | None = None,
) -> dict:
    """Edit one item within a saved meal template — rename it or change its
    calorie/macro values (e.g. bump "2 scrambled eggs" to "3 scrambled eggs" by
    updating both the name and the values). This changes the template itself, not a
    single log — future times this template is logged use the new values.

    Args:
        template_id: the template this item belongs to.
        item_id: the item to edit (from a prior get_nutrition_day/save_meal_template result).
        name: the item's new name, e.g. "3 scrambled eggs".
        values: the item's complete new value set — replaces the old one entirely,
            e.g. {"calories": 270, "protein_g": 18}.
        serving_description: optional serving note.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        await service.update_meal_template_item(
            session,
            user_sub,
            template_id=UUID(template_id),
            item_id=UUID(item_id),
            name=name,
            serving_description=serving_description,
            values={k: Decimal(str(v)) for k, v in values.items()},
        )
        return await _day_payload(session, user_sub)


@mcp.tool(app=AppConfig(resource_uri=NUTRITION_UI_URI, visibility=["model", "app"]))
@catches_service_errors
async def log_meal_template(
    template_id: str | None = None,
    name: str | None = None,
    multiplier: float = 1,
    meal_type: str | None = None,
) -> dict:
    """Log a saved meal template, optionally scaled. Portion scaling affects only this
    log instance — the template's own saved values are never changed.

    Args:
        template_id: the template to log. Provide this or name.
        name: the template's name, if you don't have its id (e.g. "my usual breakfast").
        multiplier: scales every item's values, e.g. 1.5 for one and a half portions.
        meal_type: breakfast/lunch/dinner/snack, if applicable (defaults to the
            template's own default_meal_type).
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        resolved_id = await _resolve_template_id(
            session, user_sub, template_id=template_id, name=name
        )
        await service.log_meal_template(
            session, user_sub, template_id=resolved_id, multiplier=multiplier, meal_type=meal_type
        )
        return await _day_payload(session, user_sub)


@mcp.tool
@catches_service_errors
async def get_goals() -> str:
    """Read the caller's current nutrition goals."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        goals = await service.get_goals(session, user_sub)
        if not goals:
            return "No goals set yet."
        return ", ".join(f"{g.trackable_key}: {g.target_value}" for g in goals)


@mcp.tool
@catches_service_errors
async def set_goals(goals: list[dict]) -> str:
    """Set or update any subset of nutrition goals in one call.

    Args:
        goals: [{"trackable_key": "calories", "target_value": 2200, "is_streak_target": true}, ...].
            is_streak_target is optional; at most one goal can carry it — setting it on
            one clears it from any other.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        updated = await service.set_goals(session, user_sub, goals=goals)
        return ", ".join(f"{g.trackable_key}: {g.target_value}" for g in updated)


@mcp.resource(NUTRITION_UI_URI, icons=app_icons())
def nutrition_day_ui() -> str:
    """The nutrition-day component — one bundle rendered by Claude and the SPA alike."""
    if NUTRITION_UI_BUNDLE.is_file():
        return NUTRITION_UI_BUNDLE.read_text()
    return (
        "<html><body style='font-family:system-ui;padding:1rem'>"
        "<p>The nutrition-day component bundle isn't built. Run <code>make apps</code>.</p>"
        "</body></html>"
    )
