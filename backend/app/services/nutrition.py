"""Nutrition service — logs/log_values/trackable_types/goals (#4, resolved)."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import events
from app.models.nutrition import (
    Goal,
    Log,
    LogValue,
    MealTemplate,
    MealTemplateItem,
    MealTemplateItemValue,
    TrackableType,
)


class NotFoundError(Exception):
    """Raised when a row doesn't exist *or* belongs to someone else.

    Deliberately not distinguished — telling a caller that an id exists but isn't theirs
    leaks the existence of other users' rows.
    """


async def list_trackable_types(session: AsyncSession) -> list[TrackableType]:
    result = await session.execute(select(TrackableType).order_by(TrackableType.key))
    return list(result.scalars())


async def log_nutrition(
    session: AsyncSession,
    user_sub: str,
    *,
    entries: list[dict],
    logged_at: datetime | None = None,
    name: str | None = None,
    meal_type: str | None = None,
    source: str = "manual",
) -> Log:
    log = Log(
        user_id=user_sub,
        logged_at=logged_at or datetime.now(UTC),
        source=source,
        name=name,
        meal_type=meal_type,
        edited_by_user=False,
    )
    session.add(log)
    await session.flush()

    for entry in entries:
        session.add(
            LogValue(log_id=log.id, trackable_key=entry["trackable_key"], value=entry["value"])
        )
    await session.flush()
    events.publish(user_sub, "nutrition")
    return log


async def get_log_values(session: AsyncSession, user_sub: str, log_id: uuid.UUID) -> list[LogValue]:
    result = await session.execute(
        select(LogValue)
        .join(Log, Log.id == LogValue.log_id)
        .where(LogValue.log_id == log_id, Log.user_id == user_sub)
    )
    return list(result.scalars())


async def update_nutrition_log(
    session: AsyncSession,
    user_sub: str,
    *,
    log_id: uuid.UUID,
    name: str | None = None,
    meal_type: str | None = None,
    values: dict[str, Decimal] | None = None,
) -> Log:
    """Conversational correction — "actually that was a small coffee, not a large"
    (#4/#6, resolved: the nutrition equivalent of update_workout). Only fields
    actually passed change; `values` patches individual trackable keys in place
    rather than replacing the whole set, since a correction usually touches one
    number, not the whole meal."""
    result = await session.execute(select(Log).where(Log.id == log_id, Log.user_id == user_sub))
    log = result.scalar_one_or_none()
    if log is None:
        raise NotFoundError(f"No log {log_id}")

    if name is not None:
        log.name = name
    if meal_type is not None:
        log.meal_type = meal_type
    if values:
        existing = {v.trackable_key: v for v in await get_log_values(session, user_sub, log.id)}
        for trackable_key, value in values.items():
            row = existing.get(trackable_key)
            if row is not None:
                row.value = value
            else:
                session.add(LogValue(log_id=log.id, trackable_key=trackable_key, value=value))
    log.edited_by_user = True

    await session.flush()
    events.publish(user_sub, "nutrition")
    return log


async def amend_last_log(
    session: AsyncSession,
    user_sub: str,
    *,
    name: str | None = None,
    meal_type: str | None = None,
    values: dict[str, Decimal] | None = None,
) -> tuple[Log | None, uuid.UUID, str | None]:
    """ "Undo that" / fix the single most recent entry without needing to identify
    which record (#4/#6, resolved). No fields given deletes the most recent log
    outright (the undo path); any field given patches it in place via
    update_nutrition_log instead. Returns (updated_log, log_id, name) — `updated_log`
    is None when the entry was deleted, since the row no longer exists to return.
    "Most recent" is insertion order (`created_at`), not `logged_at` — a backdated
    entry someone just logged is still the thing "that" refers to.
    """
    result = await session.execute(
        select(Log).where(Log.user_id == user_sub).order_by(Log.created_at.desc()).limit(1)
    )
    log = result.scalar_one_or_none()
    if log is None:
        raise NotFoundError("No logs to amend yet.")

    log_id, log_name = log.id, log.name
    if name is None and meal_type is None and not values:
        await session.delete(log)
        await session.flush()
        events.publish(user_sub, "nutrition")
        return None, log_id, log_name

    updated = await update_nutrition_log(
        session, user_sub, log_id=log_id, name=name, meal_type=meal_type, values=values
    )
    return updated, log_id, updated.name


async def get_goals(session: AsyncSession, user_sub: str) -> list[Goal]:
    result = await session.execute(select(Goal).where(Goal.user_id == user_sub))
    return list(result.scalars())


async def set_goals(session: AsyncSession, user_sub: str, *, goals: list[dict]) -> list[Goal]:
    """Upserts each entry by (user_sub, trackable_key). At most one goal can carry
    is_streak_target — setting one clears it from every other goal of this user's
    first, service-side (not a DB constraint — #6, resolved)."""
    if any(g.get("is_streak_target") for g in goals):
        await session.execute(
            update(Goal).where(Goal.user_id == user_sub).values(is_streak_target=False)
        )

    existing = {g.trackable_key: g for g in await get_goals(session, user_sub)}
    for entry in goals:
        goal = existing.get(entry["trackable_key"])
        if goal is None:
            goal = Goal(user_id=user_sub, trackable_key=entry["trackable_key"], target_value=0)
            session.add(goal)
        goal.target_value = entry["target_value"]
        # `entry.get(...) is not None`, not `"is_streak_target" in entry`: the REST path
        # always sends the key (GoalIn.model_dump() includes unset fields as None), so
        # `in` can't distinguish "omitted" from "explicitly null" and was overwriting an
        # existing goal's flag with NULL — a constraint violation on UPDATE (INSERT
        # happened to survive via the column's Python-side default).
        if entry.get("is_streak_target") is not None:
            goal.is_streak_target = entry["is_streak_target"]

    await session.flush()
    events.publish(user_sub, "nutrition")
    return await get_goals(session, user_sub)


@dataclass
class TrackableProgress:
    trackable_key: str
    label: str
    unit: str
    consumed: Decimal
    target: Decimal | None


@dataclass
class DayLogItem:
    id: uuid.UUID
    name: str | None
    values: dict[str, Decimal]


@dataclass
class DayLog:
    """One line in the day's log. Ungrouped (the common case): `id` is the log's own
    id, `items` stays empty. Grouped (logged via a meal template): `id` is the shared
    group_id, `name` is the template's name snapshotted at log time, `values` are the
    combined totals across every item, and `items` holds the per-item breakdown (#4,
    resolved — "the logged-history entry also shows the per-item breakdown")."""

    id: uuid.UUID
    name: str | None
    logged_at: datetime
    meal_type: str | None
    values: dict[str, Decimal] = field(default_factory=dict)
    items: list[DayLogItem] = field(default_factory=list)


@dataclass
class MealTemplateItemOut:
    id: uuid.UUID
    name: str
    serving_description: str | None
    values: dict[str, Decimal]


@dataclass
class MealTemplateSummary:
    id: uuid.UUID
    name: str
    default_meal_type: str | None
    items: list[MealTemplateItemOut]
    totals: dict[str, Decimal]


@dataclass
class NutritionDay:
    date: date
    hero: TrackableProgress
    bars: list[TrackableProgress]
    streak_key: str | None
    logs: list[DayLog]
    templates: list[MealTemplateSummary]


async def list_meal_templates(session: AsyncSession, user_sub: str) -> list[MealTemplateSummary]:
    result = await session.execute(
        select(MealTemplate, MealTemplateItem, MealTemplateItemValue)
        .join(MealTemplateItem, MealTemplateItem.template_id == MealTemplate.id)
        .outerjoin(
            MealTemplateItemValue, MealTemplateItemValue.template_item_id == MealTemplateItem.id
        )
        .where(MealTemplate.user_id == user_sub)
        .order_by(MealTemplate.updated_at.desc(), MealTemplateItem.item_order)
    )

    templates: dict[uuid.UUID, MealTemplateSummary] = {}
    items_by_template: dict[uuid.UUID, dict[uuid.UUID, MealTemplateItemOut]] = {}
    for template, item, value in result.all():
        summary = templates.get(template.id)
        if summary is None:
            summary = MealTemplateSummary(
                id=template.id,
                name=template.name,
                default_meal_type=template.default_meal_type,
                items=[],
                totals={},
            )
            templates[template.id] = summary
            items_by_template[template.id] = {}

        item_map = items_by_template[template.id]
        item_out = item_map.get(item.id)
        if item_out is None:
            item_out = MealTemplateItemOut(
                id=item.id, name=item.name, serving_description=item.serving_description, values={}
            )
            item_map[item.id] = item_out
            summary.items.append(item_out)

        if value is not None:
            item_out.values[value.trackable_key] = value.value
            summary.totals[value.trackable_key] = (
                summary.totals.get(value.trackable_key, Decimal(0)) + value.value
            )

    return list(templates.values())


async def save_meal_template(
    session: AsyncSession,
    user_sub: str,
    *,
    name: str,
    log_ids: list[uuid.UUID],
    default_meal_type: str | None = None,
    template_id: uuid.UUID | None = None,
) -> MealTemplateSummary:
    """Save-from-log only (#4, resolved) — snapshots the named/valued items of the
    caller's own already-logged entries into a template. `template_id` revises an
    existing template in place (items are replaced wholesale, not merged)."""
    template = None
    if template_id is not None:
        result = await session.execute(
            select(MealTemplate).where(
                MealTemplate.id == template_id, MealTemplate.user_id == user_sub
            )
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise NotFoundError(f"No meal template {template_id}")

    if template is None:
        template = MealTemplate(user_id=user_sub, name=name, default_meal_type=default_meal_type)
        session.add(template)
        await session.flush()
    else:
        template.name = name
        template.default_meal_type = default_meal_type
        await session.execute(
            delete(MealTemplateItem).where(MealTemplateItem.template_id == template.id)
        )

    logs_result = await session.execute(
        select(Log, LogValue)
        .outerjoin(LogValue, LogValue.log_id == Log.id)
        .where(Log.user_id == user_sub, Log.id.in_(log_ids))
    )
    logs_by_id: dict[uuid.UUID, Log] = {}
    values_by_log: dict[uuid.UUID, dict[str, Decimal]] = {}
    for log, value in logs_result.all():
        logs_by_id.setdefault(log.id, log)
        if value is not None:
            values_by_log.setdefault(log.id, {})[value.trackable_key] = value.value

    for order, log_id in enumerate(log_ids):
        log = logs_by_id.get(log_id)
        if log is None:
            continue  # not this user's log (or already gone) — skip rather than fail the batch
        item = MealTemplateItem(
            template_id=template.id,
            name=log.name or "Item",
            serving_description=log.serving_description,
            item_order=order,
        )
        session.add(item)
        await session.flush()
        for trackable_key, value in values_by_log.get(log_id, {}).items():
            session.add(
                MealTemplateItemValue(
                    template_item_id=item.id, trackable_key=trackable_key, value=value
                )
            )

    await session.flush()
    events.publish(user_sub, "nutrition")
    templates = await list_meal_templates(session, user_sub)
    return next(t for t in templates if t.id == template.id)


async def update_meal_template_item(
    session: AsyncSession,
    user_sub: str,
    *,
    template_id: uuid.UUID,
    item_id: uuid.UUID,
    name: str,
    serving_description: str | None,
    values: dict[str, Decimal],
) -> MealTemplateSummary:
    """Edits one item's contents in place — the "fix an item" action the resolution
    calls out as separate from a log-time portion stepper (#4, resolved). Full-form
    replacement, same as the shared item-card pattern used elsewhere: `values` is the
    item's complete new value set, not a patch of individual keys."""
    result = await session.execute(
        select(MealTemplate, MealTemplateItem)
        .join(MealTemplateItem, MealTemplateItem.template_id == MealTemplate.id)
        .where(
            MealTemplate.id == template_id,
            MealTemplate.user_id == user_sub,
            MealTemplateItem.id == item_id,
        )
    )
    row = result.first()
    if row is None:
        raise NotFoundError(f"No item {item_id} on template {template_id}")
    template, item = row

    item.name = name
    item.serving_description = serving_description
    template.updated_at = datetime.now(UTC)
    await session.execute(
        delete(MealTemplateItemValue).where(MealTemplateItemValue.template_item_id == item.id)
    )
    for trackable_key, value in values.items():
        session.add(
            MealTemplateItemValue(
                template_item_id=item.id, trackable_key=trackable_key, value=value
            )
        )

    await session.flush()
    events.publish(user_sub, "nutrition")
    templates = await list_meal_templates(session, user_sub)
    return next(t for t in templates if t.id == template_id)


async def delete_meal_template(
    session: AsyncSession, user_sub: str, template_id: uuid.UUID
) -> None:
    result = await session.execute(
        select(MealTemplate).where(MealTemplate.id == template_id, MealTemplate.user_id == user_sub)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundError(f"No meal template {template_id}")
    await session.delete(template)
    events.publish(user_sub, "nutrition")


async def log_meal_template(
    session: AsyncSession,
    user_sub: str,
    *,
    template_id: uuid.UUID,
    multiplier: Decimal | float | str = 1,
    meal_type: str | None = None,
    logged_at: datetime | None = None,
) -> list[Log]:
    """Writes one new Log per template item, all sharing a fresh group_id + the
    template's name snapshotted as group_name — the day view collapses them back into
    one card. Portion scaling (`multiplier`) affects only this log instance; the
    template's own item values are never touched (#4, resolved)."""
    result = await session.execute(
        select(MealTemplate).where(MealTemplate.id == template_id, MealTemplate.user_id == user_sub)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundError(f"No meal template {template_id}")

    items_result = await session.execute(
        select(MealTemplateItem, MealTemplateItemValue)
        .outerjoin(
            MealTemplateItemValue, MealTemplateItemValue.template_item_id == MealTemplateItem.id
        )
        .where(MealTemplateItem.template_id == template.id)
        .order_by(MealTemplateItem.item_order)
    )
    items: dict[uuid.UUID, MealTemplateItem] = {}
    values_by_item: dict[uuid.UUID, dict[str, Decimal]] = {}
    order: list[uuid.UUID] = []
    for item, value in items_result.all():
        if item.id not in items:
            items[item.id] = item
            values_by_item[item.id] = {}
            order.append(item.id)
        if value is not None:
            values_by_item[item.id][value.trackable_key] = value.value

    scale = Decimal(str(multiplier))
    group_id = uuid.uuid4()
    when = logged_at or datetime.now(UTC)

    created: list[Log] = []
    for item_id in order:
        item = items[item_id]
        log = Log(
            user_id=user_sub,
            logged_at=when,
            source="template",
            source_ref=str(template.id),
            group_id=group_id,
            group_name=template.name,
            name=item.name,
            serving_description=item.serving_description,
            meal_type=meal_type or template.default_meal_type,
            edited_by_user=False,
        )
        session.add(log)
        await session.flush()
        for trackable_key, value in values_by_item[item_id].items():
            session.add(LogValue(log_id=log.id, trackable_key=trackable_key, value=value * scale))
        created.append(log)

    await session.flush()
    events.publish(user_sub, "nutrition")
    return created


async def get_nutrition_day(
    session: AsyncSession, user_sub: str, day: date | None = None
) -> NutritionDay:
    """The day-vs-goals view (#4, resolved): the calorie ring is always the hero, and
    every other goal-eligible trackable always renders as a bar, whether or not a
    target's been set for it (matching the legacy TodaySummary.tsx reference this
    generalizes — `target` is just None until the caller sets one). Bounds the day in
    UTC; there's no per-user timezone yet.
    """
    day = day or datetime.now(UTC).date()
    start = datetime.combine(day, time.min, tzinfo=UTC)
    end = datetime.combine(day, time.max, tzinfo=UTC)

    result = await session.execute(
        select(Log, LogValue)
        .outerjoin(LogValue, LogValue.log_id == Log.id)
        .where(Log.user_id == user_sub, Log.logged_at >= start, Log.logged_at <= end)
        .order_by(Log.logged_at)
    )

    logs_by_id: dict[uuid.UUID, Log] = {}
    values_by_log: dict[uuid.UUID, dict[str, Decimal]] = {}
    log_order: list[uuid.UUID] = []
    totals: dict[str, Decimal] = {}
    for log, value in result.all():
        if log.id not in logs_by_id:
            logs_by_id[log.id] = log
            values_by_log[log.id] = {}
            log_order.append(log.id)
        if value is not None:
            values_by_log[log.id][value.trackable_key] = value.value
            totals[value.trackable_key] = totals.get(value.trackable_key, Decimal(0)) + value.value

    # Grouped by (group_id or the log's own id) so a template-logged meal collapses
    # into one DayLog with a per-item breakdown, while every other log — keyed
    # uniquely by its own id — passes through as a normal single-item entry.
    day_logs: dict[uuid.UUID, DayLog] = {}
    for log_id in log_order:
        log = logs_by_id[log_id]
        values = values_by_log[log_id]
        key = log.group_id or log.id
        entry = day_logs.get(key)
        if entry is None:
            entry = DayLog(
                id=key,
                name=log.group_name or log.name,
                logged_at=log.logged_at,
                meal_type=log.meal_type,
            )
            day_logs[key] = entry
        if log.group_id is not None:
            entry.items.append(DayLogItem(id=log.id, name=log.name, values=values))
        for trackable_key, v in values.items():
            entry.values[trackable_key] = entry.values.get(trackable_key, Decimal(0)) + v

    types_by_key = {t.key: t for t in await list_trackable_types(session)}
    goals_by_key = {g.trackable_key: g for g in await get_goals(session, user_sub)}
    streak_key = next((k for k, g in goals_by_key.items() if g.is_streak_target), None)

    calories = types_by_key["calories"]
    hero = TrackableProgress(
        trackable_key="calories",
        label=calories.label,
        unit=calories.unit,
        consumed=totals.get("calories", Decimal(0)),
        target=goals_by_key["calories"].target_value if "calories" in goals_by_key else None,
    )

    bars = [
        TrackableProgress(
            trackable_key=key,
            label=t.label,
            unit=t.unit,
            consumed=totals.get(key, Decimal(0)),
            target=goals_by_key[key].target_value if key in goals_by_key else None,
        )
        for key, t in types_by_key.items()
        if key != "calories" and t.goal_eligible
    ]

    return NutritionDay(
        date=day,
        hero=hero,
        bars=bars,
        streak_key=streak_key,
        logs=list(day_logs.values()),
        templates=await list_meal_templates(session, user_sub),
    )
