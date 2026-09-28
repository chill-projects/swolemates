"""Meal plan service — planning what gets eaten, and turning that into real entries.

The one idea worth holding on to is that a planned meal's macros are *derived*, and the
derivation is named. Three sources, in precedence order:

  1. rows in `planned_meal_values` — the caller typed these, so nothing overrules them;
  2. a saved meal's item totals, or a leftover's snapshot, scaled by `portion`;
  3. nothing at all, which stays nothing. An ad-hoc "dinner at Mum's" is not zero
     calories, and a day containing one reports `unestimated` rather than a total that
     quietly under-counts.

That third case is why `values` is a plain dict and `estimated` is a separate flag: an
empty dict means "we don't know", never "we know it's zero".
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meal_plan import (
    MEAL_TYPES,
    KitchenItem,
    KitchenItemKind,
    KitchenItemTemplate,
    KitchenItemValue,
    PlannedMeal,
    PlannedMealStatus,
    PlannedMealValue,
)
from app.models.nutrition import MealTemplate
from app.services import nutrition as nutrition_service
from app.services.errors import NotFoundError


@dataclass
class KitchenTemplateRef:
    id: uuid.UUID
    name: str


@dataclass
class KitchenItemOut:
    id: uuid.UUID
    kind: str
    name: str
    portion: Decimal | None
    # Already scaled by `portion` — callers want "what this is worth now", not the
    # original meal's numbers plus a multiplier to remember to apply.
    values: dict[str, Decimal]
    templates: list[KitchenTemplateRef] = field(default_factory=list)


@dataclass
class PlannedMealOut:
    id: uuid.UUID
    scheduled_for: date
    meal_type: str
    name: str
    source: str  # "template" | "leftover" | "adhoc"
    template_id: uuid.UUID | None
    kitchen_item_id: uuid.UUID | None
    portion: Decimal | None
    status: str
    log_group_id: uuid.UUID | None
    values: dict[str, Decimal]
    #: False when nobody knows this meal's macros, which is different from zero.
    estimated: bool
    #: True when `values` came from the caller rather than from the source.
    overridden: bool


@dataclass
class PlannedDayOut:
    scheduled_for: date
    meals: list[PlannedMealOut]
    totals: dict[str, Decimal]
    unestimated: int


def _slot_order(meal_type: str) -> int:
    return MEAL_TYPES.index(meal_type)


def _require_meal_type(meal_type: str) -> str:
    if meal_type not in MEAL_TYPES:
        raise ValueError(f"Unknown meal type {meal_type!r}. Use one of: {', '.join(MEAL_TYPES)}.")
    return meal_type


def _tidy(value: Decimal) -> Decimal:
    """Drop the trailing zeros scaling leaves behind, so half of 780 reads as 390 and
    not 390.0, without rounding away a real 2.5."""
    normalized = value.normalize()
    return normalized.quantize(Decimal(1)) if normalized.as_tuple().exponent > 0 else normalized


def _scale(values: dict[str, Decimal], portion: Decimal | None) -> dict[str, Decimal]:
    if portion is None or portion == 1:
        return dict(values)
    return {key: _tidy(value * portion) for key, value in values.items()}


async def _require_planned(
    session: AsyncSession, user_sub: str, planned_meal_id: uuid.UUID
) -> PlannedMeal:
    result = await session.execute(
        select(PlannedMeal).where(
            PlannedMeal.id == planned_meal_id, PlannedMeal.user_id == user_sub
        )
    )
    planned = result.scalar_one_or_none()
    if planned is None:
        raise NotFoundError(f"No planned meal {planned_meal_id}")
    return planned


async def _require_kitchen_item(
    session: AsyncSession, user_sub: str, item_id: uuid.UUID
) -> KitchenItem:
    result = await session.execute(
        select(KitchenItem).where(KitchenItem.id == item_id, KitchenItem.user_id == user_sub)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise NotFoundError(f"No kitchen item {item_id}")
    return item


async def _require_template(session: AsyncSession, user_sub: str, template_id: uuid.UUID):
    templates = await nutrition_service.list_meal_templates(session, user_sub)
    for template in templates:
        if template.id == template_id:
            return template
    raise NotFoundError(f"No meal template {template_id}")


async def _kitchen_values(session: AsyncSession, item_id: uuid.UUID) -> dict[str, Decimal]:
    result = await session.execute(
        select(KitchenItemValue).where(KitchenItemValue.kitchen_item_id == item_id)
    )
    return {v.trackable_key: v.value for v in result.scalars()}


async def _overrides(session: AsyncSession, planned_ids: list[uuid.UUID]) -> dict:
    if not planned_ids:
        return {}
    result = await session.execute(
        select(PlannedMealValue).where(PlannedMealValue.planned_meal_id.in_(planned_ids))
    )
    out: dict[uuid.UUID, dict[str, Decimal]] = {}
    for row in result.scalars():
        out.setdefault(row.planned_meal_id, {})[row.trackable_key] = row.value
    return out


async def _resolve(
    session: AsyncSession, user_sub: str, planned: PlannedMeal, override: dict[str, Decimal] | None
) -> PlannedMealOut:
    """Turn a row into the view, working out where its numbers come from."""
    if planned.template_id is not None:
        source = "template"
    elif planned.kitchen_item_id is not None:
        source = "leftover"
    else:
        source = "adhoc"

    portion = Decimal(str(planned.portion)) if planned.portion is not None else None

    if override:
        values = dict(override)
        overridden = True
    else:
        overridden = False
        base: dict[str, Decimal] = {}
        if planned.template_id is not None:
            templates = await nutrition_service.list_meal_templates(session, user_sub)
            match = next((t for t in templates if t.id == planned.template_id), None)
            base = dict(match.totals) if match else {}
        elif planned.kitchen_item_id is not None:
            base = await _kitchen_values(session, planned.kitchen_item_id)
        values = _scale(base, portion)

    return PlannedMealOut(
        id=planned.id,
        scheduled_for=planned.scheduled_for,
        meal_type=planned.meal_type,
        name=planned.name,
        source=source,
        template_id=planned.template_id,
        kitchen_item_id=planned.kitchen_item_id,
        portion=portion,
        status=str(planned.status),
        log_group_id=planned.log_group_id,
        values=values,
        estimated=bool(values),
        overridden=overridden,
    )


# ------------------------------------------------------------------------ reading


async def get_meal_plan(
    session: AsyncSession, user_sub: str, *, start: date, end: date
) -> list[PlannedDayOut]:
    """Every day in the range, empty ones included — the grid draws seven columns
    whether or not anything is in them."""
    if end < start:
        raise ValueError("`end` must not be before `start`.")

    result = await session.execute(
        select(PlannedMeal)
        .where(
            PlannedMeal.user_id == user_sub,
            PlannedMeal.scheduled_for >= start,
            PlannedMeal.scheduled_for <= end,
        )
        .order_by(PlannedMeal.scheduled_for)
    )
    rows = list(result.scalars())
    overrides = await _overrides(session, [r.id for r in rows])

    by_day: dict[date, list[PlannedMealOut]] = {}
    for row in rows:
        by_day.setdefault(row.scheduled_for, []).append(
            await _resolve(session, user_sub, row, overrides.get(row.id))
        )

    days: list[PlannedDayOut] = []
    cursor = start
    while cursor <= end:
        meals = sorted(by_day.get(cursor, []), key=lambda m: _slot_order(m.meal_type))
        totals: dict[str, Decimal] = {}
        unestimated = 0
        for meal in meals:
            if not meal.estimated:
                unestimated += 1
                continue
            for key, value in meal.values.items():
                totals[key] = totals.get(key, Decimal(0)) + value
        days.append(
            PlannedDayOut(scheduled_for=cursor, meals=meals, totals=totals, unestimated=unestimated)
        )
        cursor += timedelta(days=1)
    return days


async def resolve_meal_reference(session: AsyncSession, user_sub: str, name: str) -> dict:
    """Turn "the chicken curry" into whichever saved meal or leftover that is.

    Lives here rather than in the tool layer because it reads the caller's own data and
    decides what a request means — exactly the kind of thing that must not diverge
    between the two front doors.

    Leftovers win a tie: when both a saved meal and a leftover match, the leftover is
    almost always what someone means, because it's the thing that needs eating. Exact
    matches beat partial ones. Nothing matching is not an error — it becomes an ad-hoc
    meal with no macros, which is honest and still gets the day planned.
    """
    needle = name.strip().lower()
    kitchen = await list_kitchen(session, user_sub)
    leftovers = [i for i in kitchen if i.kind == KitchenItemKind.leftover.value]
    templates = await nutrition_service.list_meal_templates(session, user_sub)

    for item in leftovers:
        if item.name.lower() == needle:
            return {"kitchen_item_id": item.id}
    for template in templates:
        if template.name.lower() == needle:
            return {"template_id": template.id}
    for item in leftovers:
        if needle and needle in item.name.lower():
            return {"kitchen_item_id": item.id}
    for template in templates:
        if needle and needle in template.name.lower():
            return {"template_id": template.id}
    return {"name": name.strip()}


# ------------------------------------------------------------------------ writing


async def plan_meal(
    session: AsyncSession,
    user_sub: str,
    *,
    scheduled_for: date,
    meal_type: str,
    template_id: uuid.UUID | None = None,
    kitchen_item_id: uuid.UUID | None = None,
    name: str | None = None,
    portion: Decimal | None = None,
    values: dict[str, Decimal] | None = None,
) -> PlannedMealOut:
    """Put one meal in one slot, replacing whatever was there.

    Exactly one of `template_id`, `kitchen_item_id` or `name` names what's being
    planned. An ingredient is deliberately not plannable: it has no macros of its own,
    so the thing to plan is one of the saved meals that uses it.
    """
    _require_meal_type(meal_type)
    if sum(x is not None for x in (template_id, kitchen_item_id, name)) != 1:
        raise ValueError("Give exactly one of template_id, kitchen_item_id or name.")

    resolved_name = name
    if template_id is not None:
        template = await _require_template(session, user_sub, template_id)
        resolved_name = template.name
    elif kitchen_item_id is not None:
        item = await _require_kitchen_item(session, user_sub, kitchen_item_id)
        if item.kind is KitchenItemKind.ingredient:
            raise ValueError(
                f"{item.name!r} is an ingredient, not a meal. "
                "Plan one of the saved meals that uses it instead."
            )
        resolved_name = item.name
        # A leftover's portion already lives on the tray entry; carrying it onto the
        # plan means deleting the tray entry later doesn't blank the day.
        portion = portion if portion is not None else item.portion

    await _clear_slot(session, user_sub, scheduled_for, meal_type)

    planned = PlannedMeal(
        user_id=user_sub,
        scheduled_for=scheduled_for,
        meal_type=meal_type,
        name=resolved_name or "Something",
        template_id=template_id,
        kitchen_item_id=kitchen_item_id,
        portion=portion,
        status=PlannedMealStatus.planned,
    )
    session.add(planned)
    await session.flush()

    if values:
        await _write_values(session, planned.id, values)
    await session.flush()
    return await _resolve(session, user_sub, planned, values or None)


async def update_planned_meal(
    session: AsyncSession,
    user_sub: str,
    *,
    planned_meal_id: uuid.UUID,
    name: str | None = None,
    portion: Decimal | None = None,
    values: dict[str, Decimal] | None = None,
    scheduled_for: date | None = None,
    meal_type: str | None = None,
) -> PlannedMealOut:
    """Edit a planned meal in place: rename it, re-portion it, correct its macros, or
    move it to another day or slot.

    `values={}` is meaningful and distinct from `values=None`: the empty dict clears an
    override so the numbers fall back to the source, while None leaves whatever is
    there alone. Same convention `update_meal_template` uses for clearing a tag.
    """
    planned = await _require_planned(session, user_sub, planned_meal_id)

    if meal_type is not None:
        _require_meal_type(meal_type)
    target_day = scheduled_for if scheduled_for is not None else planned.scheduled_for
    target_slot = meal_type if meal_type is not None else planned.meal_type
    if (target_day, target_slot) != (planned.scheduled_for, planned.meal_type):
        await _clear_slot(session, user_sub, target_day, target_slot, keep=planned.id)
        planned.scheduled_for = target_day
        planned.meal_type = target_slot

    if name is not None:
        planned.name = name
    if portion is not None:
        planned.portion = portion
    if values is not None:
        await session.execute(
            delete(PlannedMealValue).where(PlannedMealValue.planned_meal_id == planned.id)
        )
        if values:
            await _write_values(session, planned.id, values)

    await session.flush()
    current = await _overrides(session, [planned.id])
    return await _resolve(session, user_sub, planned, current.get(planned.id))


async def clear_planned_meal(
    session: AsyncSession, user_sub: str, *, planned_meal_id: uuid.UUID
) -> None:
    planned = await _require_planned(session, user_sub, planned_meal_id)
    await session.execute(delete(PlannedMeal).where(PlannedMeal.id == planned.id))
    await session.flush()


async def log_planned_meal(
    session: AsyncSession,
    user_sub: str,
    *,
    planned_meal_id: uuid.UUID,
    logged_at: datetime | None = None,
) -> PlannedMealOut:
    """Turn a forecast into a real entry in the day.

    The entry is written from the plan's *resolved* values, so an edited plan logs the
    numbers the caller corrected rather than the source's originals. A meal nobody has
    numbers for can't be logged — there is nothing to write.
    """
    planned = await _require_planned(session, user_sub, planned_meal_id)
    if planned.status is PlannedMealStatus.logged:
        raise ValueError(f"{planned.name!r} has already been logged.")

    overrides = await _overrides(session, [planned.id])
    view = await _resolve(session, user_sub, planned, overrides.get(planned.id))
    if not view.values:
        raise ValueError(
            f"{planned.name!r} has no macros yet, so there's nothing to log. "
            "Add some first, or log it from the Nutrition tab."
        )

    when = logged_at or datetime.combine(planned.scheduled_for, datetime.min.time(), tzinfo=UTC)
    log = await nutrition_service.log_nutrition(
        session,
        user_sub,
        entries=[{"trackable_key": key, "value": value} for key, value in view.values.items()],
        logged_at=when,
        name=planned.name,
        meal_type=planned.meal_type,
        source="template" if planned.template_id else "manual",
    )
    planned.status = PlannedMealStatus.logged
    planned.log_group_id = log.group_id or log.id
    await session.flush()

    return await _resolve(session, user_sub, planned, overrides.get(planned.id))


async def _clear_slot(
    session: AsyncSession,
    user_sub: str,
    scheduled_for: date,
    meal_type: str,
    *,
    keep: uuid.UUID | None = None,
) -> None:
    """A slot holds one meal, so anything already there makes way."""
    stmt = delete(PlannedMeal).where(
        PlannedMeal.user_id == user_sub,
        PlannedMeal.scheduled_for == scheduled_for,
        PlannedMeal.meal_type == meal_type,
    )
    if keep is not None:
        stmt = stmt.where(PlannedMeal.id != keep)
    await session.execute(stmt)
    await session.flush()


async def _write_values(
    session: AsyncSession, planned_meal_id: uuid.UUID, values: dict[str, Decimal]
) -> None:
    for key, value in values.items():
        session.add(
            PlannedMealValue(
                planned_meal_id=planned_meal_id, trackable_key=key, value=Decimal(str(value))
            )
        )


# ----------------------------------------------------------------------- the tray


async def list_kitchen(session: AsyncSession, user_sub: str) -> list[KitchenItemOut]:
    result = await session.execute(
        select(KitchenItem).where(KitchenItem.user_id == user_sub).order_by(KitchenItem.created_at)
    )
    items = list(result.scalars())
    if not items:
        return []

    values_result = await session.execute(
        select(KitchenItemValue).where(KitchenItemValue.kitchen_item_id.in_([i.id for i in items]))
    )
    values: dict[uuid.UUID, dict[str, Decimal]] = {}
    for row in values_result.scalars():
        values.setdefault(row.kitchen_item_id, {})[row.trackable_key] = row.value

    links_result = await session.execute(
        select(KitchenItemTemplate, MealTemplate)
        .join(MealTemplate, MealTemplate.id == KitchenItemTemplate.template_id)
        .where(KitchenItemTemplate.kitchen_item_id.in_([i.id for i in items]))
    )
    links: dict[uuid.UUID, list[KitchenTemplateRef]] = {}
    for link, template in links_result.all():
        links.setdefault(link.kitchen_item_id, []).append(
            KitchenTemplateRef(id=template.id, name=template.name)
        )

    return [
        KitchenItemOut(
            id=item.id,
            kind=str(item.kind),
            name=item.name,
            portion=Decimal(str(item.portion)) if item.portion is not None else None,
            values=_scale(
                values.get(item.id, {}),
                Decimal(str(item.portion)) if item.portion is not None else None,
            ),
            templates=links.get(item.id, []),
        )
        for item in items
    ]


async def add_kitchen_item(
    session: AsyncSession,
    user_sub: str,
    *,
    kind: str,
    name: str,
    portion: Decimal | None = None,
    values: dict[str, Decimal] | None = None,
    template_ids: list[uuid.UUID] | None = None,
) -> KitchenItemOut:
    """Put something in the "needs eating" tray.

    A leftover takes the source meal's whole values plus how much is left; an ingredient
    takes the saved meals that use it. Passing values for an ingredient is a mistake
    worth naming rather than silently dropping.
    """
    if kind not in (k.value for k in KitchenItemKind):
        raise ValueError(f"Unknown kind {kind!r}. Use 'leftover' or 'ingredient'.")
    if kind == KitchenItemKind.ingredient.value and values:
        raise ValueError("An ingredient has no macros of its own — leave values off.")
    if not name.strip():
        raise ValueError("Give it a name.")

    item = KitchenItem(
        user_id=user_sub,
        kind=KitchenItemKind(kind),
        name=name.strip(),
        portion=portion,
    )
    session.add(item)
    await session.flush()

    for key, value in (values or {}).items():
        session.add(
            KitchenItemValue(kitchen_item_id=item.id, trackable_key=key, value=Decimal(str(value)))
        )
    for template_id in template_ids or []:
        await _require_template(session, user_sub, template_id)
        session.add(KitchenItemTemplate(kitchen_item_id=item.id, template_id=template_id))
    await session.flush()

    found = [i for i in await list_kitchen(session, user_sub) if i.id == item.id]
    return found[0]


async def update_kitchen_item(
    session: AsyncSession,
    user_sub: str,
    *,
    item_id: uuid.UUID,
    name: str | None = None,
    portion: Decimal | None = None,
) -> KitchenItemOut:
    item = await _require_kitchen_item(session, user_sub, item_id)
    if name is not None:
        item.name = name.strip()
    if portion is not None:
        item.portion = portion
    await session.flush()
    return [i for i in await list_kitchen(session, user_sub) if i.id == item.id][0]


async def remove_kitchen_item(session: AsyncSession, user_sub: str, *, item_id: uuid.UUID) -> None:
    """Take something out of the tray.

    Any plan that already referenced it keeps its snapshotted name and portion — the
    foreign key is SET NULL, and the resolved values were copied onto the plan when it
    stopped being derivable. Losing the tray entry must not blank out a planned day.
    """
    item = await _require_kitchen_item(session, user_sub, item_id)

    planned_result = await session.execute(
        select(PlannedMeal).where(
            PlannedMeal.user_id == user_sub, PlannedMeal.kitchen_item_id == item.id
        )
    )
    planned_rows = list(planned_result.scalars())
    if planned_rows:
        base = await _kitchen_values(session, item.id)
        existing = await _overrides(session, [p.id for p in planned_rows])
        for planned in planned_rows:
            if planned.id in existing:
                continue
            frozen = _scale(
                base, Decimal(str(planned.portion)) if planned.portion is not None else None
            )
            if frozen:
                await _write_values(session, planned.id, frozen)

    await session.execute(delete(KitchenItem).where(KitchenItem.id == item.id))
    await session.flush()


__all__ = [
    "KitchenItemOut",
    "KitchenTemplateRef",
    "NotFoundError",
    "PlannedDayOut",
    "PlannedMealOut",
    "add_kitchen_item",
    "clear_planned_meal",
    "get_meal_plan",
    "list_kitchen",
    "log_planned_meal",
    "plan_meal",
    "remove_kitchen_item",
    "resolve_meal_reference",
    "update_kitchen_item",
    "update_planned_meal",
]
