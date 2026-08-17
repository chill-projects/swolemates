"""The trackable-type catalog (#4, resolved) — foundational, shared by goals and the
day view alike, so it gets its own module rather than living under either.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.nutrition import TrackableType


async def list_trackable_types(session: AsyncSession) -> list[TrackableType]:
    result = await session.execute(select(TrackableType).order_by(TrackableType.key))
    return list(result.scalars())
