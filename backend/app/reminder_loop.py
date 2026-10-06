"""The scheduler, such as it is: a task in the web process that wakes up and asks
`reminders.send_due_reminders` whether anyone's local clock has reached their hour.

Not a Railway cron service, because Railway cron runs a service's start command and
expects it to exit — that means a second, billable service to run a query that takes
milliseconds. And not something that needs to be a singleton, because it isn't one: the
claim in `reminders._claim` decides who actually sends, so every replica ticking is
harmless. That's the trade this whole feature is built on — pay for the invariant once,
in the database, and the deployment topology stops mattering.

Interval, not a cron expression. Fifteen minutes is fine granularity for "Sunday
evening" and it's what makes half-hour zones (India, Nepal, Chatham) land on the right
hour rather than up to 45 minutes late.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from app.config import get_settings
from app.db import get_sessionmaker
from app.services import reminders

log = logging.getLogger(__name__)

TICK_SECONDS = 15 * 60


async def tick() -> int:
    """One pass. Returns how many users were notified.

    A session per user, not one for the whole tick: the commit at each boundary is what
    makes the claim binding, and it means one user's dead subscription or slow push
    service can't roll back or stall anyone else's.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        due = await reminders.due_user_ids(session)

    notified = 0
    for user_sub in due:
        try:
            async with sessionmaker() as session:
                sent = await reminders.claim_and_send(session, user_sub)
                await session.commit()
            notified += int(sent)
        except Exception:
            log.exception("weekly reminder failed for %s", user_sub)
    return notified


async def _tick_forever() -> None:
    while True:
        await asyncio.sleep(TICK_SECONDS)
        try:
            notified = await tick()
            if notified:
                log.info("weekly reminder sent to %d user(s)", notified)
        except asyncio.CancelledError:
            raise
        except Exception:
            # A failed tick must never end the loop: the next one is fifteen minutes
            # away and will retry whoever is still unclaimed.
            log.exception("weekly reminder tick failed")


@asynccontextmanager
async def reminder_loop() -> AsyncIterator[None]:
    """Runs for the life of the app, or not at all when push isn't configured — which is
    every local dev session without VAPID keys, and is why this checks rather than
    spinning a task that can only ever no-op."""
    if not get_settings().push_enabled:
        log.info("weekly reminder loop not started: %s", reminders.push_status())
        yield
        return

    task = asyncio.create_task(_tick_forever(), name="weekly-reminder-loop")
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
