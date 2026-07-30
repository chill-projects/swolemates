"""TmpxService — the template for every service in this app.

Both the REST router and the MCP tools call these functions. Note that `user_sub` is a
required first argument on every one of them and is applied as a filter inside, not by
the caller. That is the whole permission model: a transport can't forget to scope a
query because it never writes one.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import events
from app.models.tmpx import TmpxItem


class NotFoundError(Exception):
    """Raised when a row doesn't exist *or* belongs to someone else.

    Deliberately not distinguished — telling a caller that an id exists but isn't theirs
    leaks the existence of other users' rows.
    """


async def list_items(session: AsyncSession, user_sub: str, *, limit: int = 50) -> list[TmpxItem]:
    result = await session.execute(
        select(TmpxItem)
        .where(TmpxItem.user_id == user_sub)
        .order_by(TmpxItem.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def add_item(session: AsyncSession, user_sub: str, *, name: str, value: int = 0) -> TmpxItem:
    name = name.strip()
    if not name:
        raise ValueError("name must not be empty")

    item = TmpxItem(user_id=user_sub, name=name, value=value)
    session.add(item)
    await session.flush()
    events.publish(user_sub, "tmpx")
    return item


async def get_item(session: AsyncSession, user_sub: str, item_id: uuid.UUID) -> TmpxItem:
    result = await session.execute(
        select(TmpxItem).where(TmpxItem.id == item_id, TmpxItem.user_id == user_sub)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise NotFoundError(f"No tmpx item {item_id}")
    return item


async def delete_item(session: AsyncSession, user_sub: str, item_id: uuid.UUID) -> None:
    item = await get_item(session, user_sub, item_id)
    await session.delete(item)
    events.publish(user_sub, "tmpx")
