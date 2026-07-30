"""In-process change notifications, per user.

Mutations publish; SSE subscribers wake up and tell clients to refetch. Payloads are
deliberately just a topic string — subscribers refetch through the normal (authz'd)
service path, so a bug here can never leak another user's data.

Scope: correct for a single process. At >1 uvicorn worker or >1 Railway replica,
events published in one process won't reach subscribers on another — swap the
registry for Postgres LISTEN/NOTIFY at that point (see docs/design.md scaling notes).
"""

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

_subscribers: defaultdict[str, set[asyncio.Queue[str]]] = defaultdict(set)


def publish(user_sub: str, topic: str) -> None:
    for queue in _subscribers.get(user_sub, ()):  # noqa: B905
        # Non-blocking: a slow consumer drops events rather than backing up mutations.
        # Fine, because events carry no data — the next one triggers the same refetch.
        try:
            queue.put_nowait(topic)
        except asyncio.QueueFull:
            pass


@asynccontextmanager
async def subscribe(user_sub: str) -> AsyncIterator[asyncio.Queue[str]]:
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=16)
    _subscribers[user_sub].add(queue)
    try:
        yield queue
    finally:
        _subscribers[user_sub].discard(queue)
        if not _subscribers[user_sub]:
            del _subscribers[user_sub]
