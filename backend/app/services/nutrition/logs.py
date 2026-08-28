"""Single-entry nutrition logging + chat-side corrections (#4/#6, resolved)."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import events
from app.models.nutrition import Log, LogValue
from app.services.errors import NotFoundError


def _round_trackable_value(trackable_key: str, value: object) -> Decimal:
    """Nutrition-facts precision, not the ~15-digit float noise an external source
    can hand back (search_food_facts scales Open Food Facts' per-100g figures to the
    reported serving in floating point, e.g. 3.90000009536743) — whole calories,
    everything else (grams) to one decimal place."""
    decimal_value = Decimal(str(value))
    if trackable_key == "calories":
        return decimal_value.quantize(Decimal("1"))
    return decimal_value.quantize(Decimal("0.1"))


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
        trackable_key = entry["trackable_key"]
        session.add(
            LogValue(
                log_id=log.id,
                trackable_key=trackable_key,
                value=_round_trackable_value(trackable_key, entry["value"]),
            )
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


async def get_latest_trackable_value(
    session: AsyncSession, user_sub: str, trackable_key: str
) -> Decimal | None:
    """Most recently logged value for one trackable key — e.g. the caller's current
    weight, for the TDEE calculator (#19). Ordered by `logged_at`, not insertion
    order: a weigh-in is meaningfully "current" by when it happened, not when it
    was typed in."""
    result = await session.execute(
        select(LogValue.value)
        .join(Log, Log.id == LogValue.log_id)
        .where(Log.user_id == user_sub, LogValue.trackable_key == trackable_key)
        .order_by(Log.logged_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_trackable_history(
    session: AsyncSession, user_sub: str, trackable_key: str, *, since: datetime
) -> list[tuple[datetime, Decimal]]:
    """Every logged value for one key since `since`, oldest first — the weight series
    behind the Profile page's trend. Ordered by `logged_at` for the same reason
    `get_latest_trackable_value` is: a weigh-in belongs to when it happened."""
    result = await session.execute(
        select(Log.logged_at, LogValue.value)
        .join(LogValue, Log.id == LogValue.log_id)
        .where(
            Log.user_id == user_sub,
            LogValue.trackable_key == trackable_key,
            Log.logged_at >= since,
        )
        .order_by(Log.logged_at.asc())
    )
    return [(logged_at, value) for logged_at, value in result.all()]


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
            rounded_value = _round_trackable_value(trackable_key, value)
            row = existing.get(trackable_key)
            if row is not None:
                row.value = rounded_value
            else:
                session.add(
                    LogValue(log_id=log.id, trackable_key=trackable_key, value=rounded_value)
                )
    log.edited_by_user = True

    await session.flush()
    events.publish(user_sub, "nutrition")
    return log


async def delete_nutrition_log(session: AsyncSession, user_sub: str, log_id: uuid.UUID) -> None:
    """Self-service delete for a mistakenly-logged entry — the general case of
    amend_last_log's no-fields-given branch, for any entry, not just the latest."""
    result = await session.execute(select(Log).where(Log.id == log_id, Log.user_id == user_sub))
    log = result.scalar_one_or_none()
    if log is None:
        raise NotFoundError(f"No log {log_id}")
    await session.delete(log)
    await session.flush()
    events.publish(user_sub, "nutrition")


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
