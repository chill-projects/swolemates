"""Meal templates (#4, resolved) — save-from-log only, edited on both surfaces."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import events
from app.models.nutrition import (
    Log,
    LogValue,
    MealTemplate,
    MealTemplateItem,
    MealTemplateItemValue,
)
from app.services.errors import NotFoundError


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
