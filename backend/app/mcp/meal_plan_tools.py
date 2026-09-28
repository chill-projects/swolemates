"""Meal plan tools — the chat side of the Plan tab's eating half.

Task-shaped rather than a REST mirror, same as everywhere else here: `plan_meal` takes
a meal *name* and resolves it against the caller's saved meals and kitchen tray, because
"put the chicken curry on Thursday" is the sentence, not "POST a template_id". The ids
still work when a component has one.

`update_planned_meal` carries the macro edit. It matters that Claude can do this: the
common correction is "actually that was more like 650 calories", and a planner Claude
can fill but not fix would be worse than one it can't touch at all.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from app.auth import mcp_user_sub
from app.mcp._adapter import catches_service_errors, tool_session
from app.mcp.server import mcp
from app.services import meal_plan as service
from app.services import nutrition as nutrition_service
from app.services import profile as profile_service
from app.services.errors import NotFoundError
from app.services.timezones import today_in


def _meal_payload(m: service.PlannedMealOut) -> dict:
    return {
        "id": str(m.id),
        "scheduled_for": m.scheduled_for.isoformat(),
        "meal_type": m.meal_type,
        "name": m.name,
        "source": m.source,
        "portion": str(m.portion) if m.portion is not None else None,
        "status": m.status,
        "values": {k: str(v) for k, v in m.values.items()},
        "estimated": m.estimated,
        "overridden": m.overridden,
    }


def _day_payload(d: service.PlannedDayOut) -> dict:
    return {
        "scheduled_for": d.scheduled_for.isoformat(),
        "meals": [_meal_payload(m) for m in d.meals],
        "totals": {k: str(v) for k, v in d.totals.items()},
        "unestimated": d.unestimated,
    }


def _kitchen_payload(i: service.KitchenItemOut) -> dict:
    return {
        "id": str(i.id),
        "kind": i.kind,
        "name": i.name,
        "portion": str(i.portion) if i.portion is not None else None,
        "values": {k: str(v) for k, v in i.values.items()},
        "uses_in_meals": [t.name for t in i.templates],
    }


def _decimals(values: dict | None) -> dict[str, Decimal] | None:
    if values is None:
        return None
    return {key: Decimal(str(value)) for key, value in values.items()}


@mcp.tool
@catches_service_errors
async def get_meal_plan(start: str | None = None, end: str | None = None) -> dict:
    """What's planned to eat, day by day. Defaults to the next 7 days.

    Each day carries its planned meals, the totals of the ones whose macros are known,
    and `unestimated` — how many meals have no numbers yet. A day with an unestimated
    meal is under-counted, not wrong.

    Args:
        start: ISO date. Defaults to today in the caller's timezone.
        end: ISO date. Defaults to 6 days after `start`.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        tz = await profile_service.get_user_timezone(session, user_sub)
        first = date.fromisoformat(start) if start else today_in(tz)
        last = date.fromisoformat(end) if end else first + timedelta(days=6)
        days = await service.get_meal_plan(session, user_sub, start=first, end=last)
    return {"days": [_day_payload(d) for d in days]}


@mcp.tool
@catches_service_errors
async def plan_meal(
    scheduled_for: str,
    meal_type: str,
    meal: str | None = None,
    template_id: str | None = None,
    kitchen_item_id: str | None = None,
    portion: float | str | None = None,
) -> dict:
    """Put a meal on a day. A slot holds one meal, so this replaces whatever was there.

    Args:
        scheduled_for: ISO date, e.g. "2026-10-01".
        meal_type: "breakfast" | "lunch" | "dinner" | "snack".
        meal: the name of a saved meal or of something in the "needs eating" tray —
            what you'd say out loud. Matched against leftovers first. If nothing
            matches it is planned by name with no macros, which is fine and honest.
        template_id: a saved meal's id, when you already have one.
        kitchen_item_id: a leftover's id, when you already have one.
        portion: fraction of the meal, e.g. 0.5 for half. Defaults to the leftover's
            own remaining portion, or the whole saved meal.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        target: dict = {}
        if template_id:
            target = {"template_id": UUID(template_id)}
        elif kitchen_item_id:
            target = {"kitchen_item_id": UUID(kitchen_item_id)}
        elif meal:
            target = await service.resolve_meal_reference(session, user_sub, meal)
        else:
            return "Say what to plan: a meal name, a template_id, or a kitchen_item_id."

        planned = await service.plan_meal(
            session,
            user_sub,
            scheduled_for=date.fromisoformat(scheduled_for),
            meal_type=meal_type,
            portion=Decimal(str(portion)) if portion is not None else None,
            **target,
        )
    return _meal_payload(planned)


@mcp.tool
@catches_service_errors
async def update_planned_meal(
    planned_meal_id: str,
    name: str | None = None,
    portion: float | str | None = None,
    values: dict | None = None,
    scheduled_for: str | None = None,
    meal_type: str | None = None,
) -> dict:
    """Change a planned meal: rename it, re-portion it, correct its macros, or move it
    to a different day or slot.

    Args:
        planned_meal_id: from a get_meal_plan result.
        name: a new name for this one planned meal. The saved meal it came from is
            untouched.
        portion: fraction of the meal, e.g. 0.75.
        values: macros to use instead of the derived ones, e.g.
            {"calories": 650, "protein_g": 60}. Pass {} to drop a previous correction
            and go back to whatever the meal itself says.
        scheduled_for: ISO date to move it to.
        meal_type: slot to move it to.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        planned = await service.update_planned_meal(
            session,
            user_sub,
            planned_meal_id=UUID(planned_meal_id),
            name=name,
            portion=Decimal(str(portion)) if portion is not None else None,
            values=_decimals(values),
            scheduled_for=date.fromisoformat(scheduled_for) if scheduled_for else None,
            meal_type=meal_type,
        )
    return _meal_payload(planned)


@mcp.tool
@catches_service_errors
async def clear_planned_meal(planned_meal_id: str) -> str:
    """Take a meal off the plan, emptying that slot.

    Args:
        planned_meal_id: from a get_meal_plan result.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        await service.clear_planned_meal(session, user_sub, planned_meal_id=UUID(planned_meal_id))
    return "Cleared."


@mcp.tool
@catches_service_errors
async def log_planned_meal(planned_meal_id: str) -> dict:
    """Write a planned meal into the day's food log, as planned.

    Uses the plan's own numbers, including any correction made to them. A meal with no
    macros can't be logged — there's nothing to write.

    Args:
        planned_meal_id: from a get_meal_plan result.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        planned = await service.log_planned_meal(
            session, user_sub, planned_meal_id=UUID(planned_meal_id)
        )
    return _meal_payload(planned)


@mcp.tool
@catches_service_errors
async def list_kitchen() -> dict:
    """What's waiting to be eaten: leftovers with their remaining macros, and
    ingredients with the saved meals that use them."""
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        items = await service.list_kitchen(session, user_sub)
    return {"items": [_kitchen_payload(i) for i in items]}


@mcp.tool
@catches_service_errors
async def add_kitchen_item(
    kind: str,
    name: str,
    portion: float | str | None = None,
    values: dict | None = None,
    uses_in_meals: list[str] | None = None,
) -> dict:
    """Put something in the "needs eating" tray.

    Two kinds, and the difference matters. A `leftover` is a meal that already exists
    with some left — it has macros and can be planned straight onto a day. An
    `ingredient` has no macros of its own; it points at saved meals that use it, and
    planning means planning one of those.

    Args:
        kind: "leftover" | "ingredient".
        name: what it is, e.g. "Chicken curry" or "Half a cabbage".
        portion: for a leftover, how much is left as a fraction, e.g. 0.5.
        values: for a leftover, the *whole* meal's macros, e.g.
            {"calories": 780, "protein_g": 48}. `portion` scales them on read, so give
            the full numbers here rather than pre-halving them.
        uses_in_meals: for an ingredient, the names of saved meals that use it.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        template_ids = []
        for meal_name in uses_in_meals or []:
            templates = await nutrition_service.list_meal_templates(session, user_sub)
            match = next(
                (t for t in templates if t.name.lower() == meal_name.strip().lower()), None
            )
            if match is None:
                raise NotFoundError(f"No saved meal called {meal_name!r}")
            template_ids.append(match.id)

        item = await service.add_kitchen_item(
            session,
            user_sub,
            kind=kind,
            name=name,
            portion=Decimal(str(portion)) if portion is not None else None,
            values=_decimals(values),
            template_ids=template_ids or None,
        )
    return _kitchen_payload(item)


@mcp.tool
@catches_service_errors
async def remove_kitchen_item(item_id: str) -> str:
    """Take something out of the "needs eating" tray — eaten, or thrown out.

    Any day it was already planned on keeps its name and numbers.

    Args:
        item_id: from a list_kitchen result.
    """
    user_sub = mcp_user_sub()
    async with tool_session() as session:
        await service.remove_kitchen_item(session, user_sub, item_id=UUID(item_id))
    return "Removed."
