"""Nutrition tools (#4). log_nutrition and get_nutrition_day both render the day-vs-
goals view via ui://swolemates/nutrition-day.html — any call that changes a day's
totals returns the full current picture, so the component re-renders from any result
without an extra round trip (the tmpx pattern). get_goals/set_goals stay text-only
permanently, per claude-tools-v1.md §3.4.

Every tool here takes an optional `date`, mirroring log_workout/log_activity's. The
service layer always accepted `logged_at`/`day`; only this layer didn't pass them,
which is what made "I forgot to log yesterday" impossible from chat while the same
write worked fine over REST. The day a tool returns is the day it *acted on*, not
today — backdating a meal and getting today's untouched card back reads as the call
having done nothing.
"""

from datetime import date as date_type
from datetime import datetime
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
from app.services import profile as profile_service
from app.services.timezones import local_date, parse_local_datetime

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


async def _resolve_date(
    session, user_sub: str, date: str | None
) -> tuple[datetime | None, date_type | None]:
    """An ISO date/datetime from the caller -> (instant to store, local day to show).
    (None, None) when nothing was passed, letting the service default to now/today in
    the caller's own zone.

    Both halves are needed and neither substitutes for the other: an 8pm-local meal is
    already tomorrow in UTC, so the card to hand back is the day the *instant* lands on
    locally — not the raw string, and not the server's date.
    """
    if date is None:
        return None, None
    tz = await profile_service.get_user_timezone(session, user_sub)
    when = parse_local_datetime(date, tz)
    return when, local_date(when, tz)


async def _day_payload(session, user_sub: str, day: date_type | None = None) -> dict:
    day = await service.get_nutrition_day(session, user_sub, day=day)
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
async def get_nutrition_day(date: str | None = None) -> dict:
    """Show a day's nutrition against the caller's goals — today by default, or any
    past day, for "what did I eat Tuesday?" and for checking a backfill landed.

    Args:
        date: ISO date, e.g. "2026-09-08". Defaults to today in the caller's timezone.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        _when, day = await _resolve_date(session, user_sub, date)
        return await _day_payload(session, user_sub, day)


@mcp.tool(app=AppConfig(resource_uri=NUTRITION_UI_URI, visibility=["model", "app"]))
@catches_service_errors
async def log_nutrition(
    entries: list[dict],
    name: str | None = None,
    meal_type: str | None = None,
    date: str | None = None,
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
            Infer it rather than defaulting to "snack": from what the user said, or
            failing that from the time `date` resolves to (the current time when it's
            omitted). Everything's still editable afterward from the log list, so a
            wrong guess isn't costly, but "snack" as a lazy catch-all for everything
            unstated is worse than a reasonable time-of-day guess.
        date: ISO date/datetime if backdating; defaults to now. A bare date ("2026-09-08")
            is taken as that day in the user's timezone. This is the tool for "I forgot
            to log yesterday" — backfill it rather than declining or logging it as
            today, which would put the food on the wrong day's totals. Resolve relative
            words against the user's own timezone, and say which day you logged to, so a
            wrong read of "last night" is caught immediately. Include the time when they
            gave you one ("2026-09-08T19:30") — a bare date lands at local noon, which
            makes every backfilled meal look like lunch.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        when, day = await _resolve_date(session, user_sub, date)
        await service.log_nutrition(
            session,
            user_sub,
            entries=entries,
            name=name,
            meal_type=meal_type,
            logged_at=when,
            source="manual",
        )
        return await _day_payload(session, user_sub, day)


@mcp.tool
@catches_service_errors
async def update_nutrition_log(
    log_id: str,
    name: str | None = None,
    meal_type: str | None = None,
    values: dict[str, float] | None = None,
    date: str | None = None,
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
        date: ISO date/datetime to *move* the entry to — "that was yesterday's dinner,
            not today's". Moves a saved-meal entry's items together, since they were
            one sitting. Omit to leave the entry on the day it's already on.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        when, _day = await _resolve_date(session, user_sub, date)
        log = await service.update_nutrition_log(
            session,
            user_sub,
            log_id=UUID(log_id),
            name=name,
            meal_type=meal_type,
            values={k: Decimal(str(v)) for k, v in (values or {}).items()},
            logged_at=when,
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
    date: str | None = None,
) -> str:
    """Undo or fix the single most recent nutrition entry, without needing its id —
    "undo that" or "actually that was 300 calories." Pass nothing to remove the entry
    outright; pass any field to correct it in place instead.

    Args:
        name: new name, if correcting (omit to leave alone, or to just undo).
        meal_type: new meal_type, if correcting.
        values: trackable_key -> new value, for whichever macros were wrong.
        date: ISO date/datetime to move the entry to — "that was yesterday, not today".
            Counts as a correction, so passing only this patches rather than deletes.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        when, _day = await _resolve_date(session, user_sub, date)
        updated, log_id, log_name = await service.amend_last_log(
            session,
            user_sub,
            name=name,
            meal_type=meal_type,
            values={k: Decimal(str(v)) for k, v in (values or {}).items()},
            logged_at=when,
        )
        if updated is None:
            return f'Removed "{log_name or "that entry"}" from the log.'
        log_values = await service.get_log_values(session, user_sub, log_id)
    macros = ", ".join(f"{v.trackable_key}={v.value}" for v in log_values) or "no values"
    return f'Updated "{updated.name or "entry"}" — {macros}.'


@mcp.tool(app=AppConfig(resource_uri=NUTRITION_UI_URI, visibility=["app"]))
@catches_service_errors
async def delete_nutrition_log(log_id: str, date: str | None = None) -> dict:
    """App-only: delete a logged entry outright — driven by the log list's own
    delete control (with its own confirm step), not a chat entry point. Kept off
    the model's tool list on purpose, same as delete_meal_template; for a chat-
    driven undo, amend_last_log (most-recent-only) is still the right tool.

    Args:
        log_id: the entry to delete (from a prior log_nutrition/get_nutrition_day result).
        date: the day whose card to return, if not today — pass the day you're already
            showing so an edit doesn't jump the view back to today. Doesn't affect what
            this call changes.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        _when, day = await _resolve_date(session, user_sub, date)
        await service.delete_nutrition_log(session, user_sub, UUID(log_id))
        return await _day_payload(session, user_sub, day)


@mcp.tool(app=AppConfig(resource_uri=NUTRITION_UI_URI, visibility=["model", "app"]))
@catches_service_errors
async def save_meal_template(
    name: str,
    log_ids: list[str],
    default_meal_type: str | None = None,
    template_id: str | None = None,
    date: str | None = None,
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
        date: the day whose card to return, if not today — pass the day you're already
            showing so an edit doesn't jump the view back to today. Doesn't affect what
            this call changes.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        _when, day = await _resolve_date(session, user_sub, date)
        await service.save_meal_template(
            session,
            user_sub,
            name=name,
            log_ids=[UUID(i) for i in log_ids],
            default_meal_type=default_meal_type,
            template_id=UUID(template_id) if template_id else None,
        )
        return await _day_payload(session, user_sub, day)


@mcp.tool(app=AppConfig(resource_uri=NUTRITION_UI_URI, visibility=["model", "app"]))
@catches_service_errors
async def update_meal_template(
    template_id: str,
    name: str | None = None,
    default_meal_type: str | None = None,
    date: str | None = None,
) -> dict:
    """Rename a saved meal template or change which meal it defaults to, without
    touching its items — "my usual breakfast is actually a lunch." Use
    save_meal_template (with template_id) instead when the template's *contents*
    are what's changing, and update_meal_template_item for one item's numbers.

    Args:
        template_id: the template to edit.
        name: the template's new name, if it's changing.
        default_meal_type: breakfast/lunch/dinner/snack, if that's changing. Pass
            an empty string to clear it back to no default; omit it to leave
            whatever's set alone.
        date: the day whose card to return, if not today — pass the day you're already
            showing so an edit doesn't jump the view back to today. Doesn't affect what
            this call changes.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        _when, day = await _resolve_date(session, user_sub, date)
        await service.update_meal_template(
            session,
            user_sub,
            template_id=UUID(template_id),
            name=name,
            default_meal_type=default_meal_type,
        )
        return await _day_payload(session, user_sub, day)


@mcp.tool(app=AppConfig(resource_uri=NUTRITION_UI_URI, visibility=["app"]))
@catches_service_errors
async def delete_meal_template(template_id: str, date: str | None = None) -> dict:
    """App-only: delete a saved meal template — driven by the template card's own
    delete control (with its own confirm step), not a chat entry point. Kept off the
    model's tool list on purpose so a casual mention in conversation ("get rid of
    that") can't delete something; matches archive_workout_template's precedent for
    the analogous workout-template action.

    Args:
        template_id: the template to delete.
        date: the day whose card to return, if not today — pass the day you're already
            showing so an edit doesn't jump the view back to today. Doesn't affect what
            this call changes.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        _when, day = await _resolve_date(session, user_sub, date)
        await service.delete_meal_template(session, user_sub, UUID(template_id))
        return await _day_payload(session, user_sub, day)


@mcp.tool(app=AppConfig(resource_uri=NUTRITION_UI_URI, visibility=["model", "app"]))
@catches_service_errors
async def update_meal_template_item(
    template_id: str,
    item_id: str,
    name: str,
    values: dict[str, float],
    serving_description: str | None = None,
    date: str | None = None,
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
        date: the day whose card to return, if not today — pass the day you're already
            showing so an edit doesn't jump the view back to today. Doesn't affect what
            this call changes.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        _when, day = await _resolve_date(session, user_sub, date)
        await service.update_meal_template_item(
            session,
            user_sub,
            template_id=UUID(template_id),
            item_id=UUID(item_id),
            name=name,
            serving_description=serving_description,
            values={k: Decimal(str(v)) for k, v in values.items()},
        )
        return await _day_payload(session, user_sub, day)


@mcp.tool(app=AppConfig(resource_uri=NUTRITION_UI_URI, visibility=["model", "app"]))
@catches_service_errors
async def log_meal_template(
    template_id: str | None = None,
    name: str | None = None,
    multiplier: float = 1,
    meal_type: str | None = None,
    date: str | None = None,
) -> dict:
    """Log a saved meal template, optionally scaled. Portion scaling affects only this
    log instance — the template's own saved values are never changed.

    Args:
        template_id: the template to log. Provide this or name.
        name: the template's name, if you don't have its id (e.g. "my usual breakfast").
        multiplier: scales every item's values, e.g. 1.5 for one and a half portions.
        meal_type: breakfast/lunch/dinner/snack, if applicable (defaults to the
            template's own default_meal_type).
        date: ISO date/datetime if backdating — same as log_nutrition's, for backfilling
            a usual meal onto a day that went unlogged. Defaults to now.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        when, day = await _resolve_date(session, user_sub, date)
        resolved_id = await _resolve_template_id(
            session, user_sub, template_id=template_id, name=name
        )
        await service.log_meal_template(
            session,
            user_sub,
            template_id=resolved_id,
            multiplier=multiplier,
            meal_type=meal_type,
            logged_at=when,
        )
        return await _day_payload(session, user_sub, day)


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
