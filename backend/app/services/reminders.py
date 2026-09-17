"""The weekly reminder — one push, Sunday evening, "come plan your week".

Deliberately one notification kind rather than a notification *system*. That keeps three
things small enough to reason about: there is no preferences table (two columns on the
profile), no delivery ledger (one of those columns doubles as the lock), and no
scheduler service (a ticker in the existing process — see `app.reminder_loop`).

The whole concurrency story is `_claim`: a conditional UPDATE that advances
`weekly_reminder_sent_on` only if it isn't already today. Every replica ticks, every
replica tries, exactly one gets a row back, and that one sends. Same lesson as the
partner races — make the invariant something the database decides, and having N of
something stops being a design problem.

Push is off entirely when VAPID keys aren't configured, which is the local default.
Nothing here raises in that case; `send_due_reminders` returns 0 and subscribing tells
the caller why.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import date

from pywebpush import WebPushException, webpush
from sqlalchemy import Date, cast, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.profile import UserProfile
from app.models.push import PushSubscription
from app.services import profile as profile_service
from app.services import weekly_checkin

log = logging.getLogger(__name__)

# Sunday. Matches `date.weekday()`, which `services/timezones.py` and the weekly pattern
# already use, so "day 6" means the same thing everywhere in this codebase.
REMINDER_WEEKDAY = 6
DEFAULT_REMINDER_HOUR = 18

# How long a push service is asked to hold the message for a device that's offline. A
# Sunday planning nudge is worthless by Tuesday; better it quietly expires than arrives
# stale.
PUSH_TTL_SECONDS = 6 * 60 * 60


@dataclass
class ReminderSettings:
    enabled: bool
    hour: int | None
    subscribed_devices: int


def _local_now(tz_column, part: str):
    """`EXTRACT(part FROM now() AT TIME ZONE <the user's own zone>)`.

    Done in SQL rather than by pulling every profile into Python and looping: the set of
    users whose local clock currently reads Sunday 18:00 is a query, and writing it as
    one keeps the tick O(due users) instead of O(all users).
    """
    local = func.timezone(func.coalesce(tz_column, "UTC"), func.now())
    return func.extract(part, local)


async def due_user_ids(session: AsyncSession, *, weekday: int | None = None) -> list[str]:
    """Everyone whose local time is right now the hour they asked for, on the reminder
    weekday, who hasn't already been sent one for their local date.

    The `sent_on` check here only keeps the candidate list short — it is not what
    prevents a double send. `_claim` is.

    `weekday` is resolved at call time rather than defaulted in the signature, so the
    module constant stays overridable (a default argument would bind REMINDER_WEEKDAY
    once, at import).
    """
    weekday = REMINDER_WEEKDAY if weekday is None else weekday
    local_date = cast(func.timezone(func.coalesce(UserProfile.timezone, "UTC"), func.now()), Date)
    result = await session.execute(
        select(UserProfile.user_id).where(
            UserProfile.weekly_reminder_hour.isnot(None),
            _local_now(UserProfile.timezone, "dow") == (weekday + 1) % 7,
            _local_now(UserProfile.timezone, "hour") == UserProfile.weekly_reminder_hour,
            (UserProfile.weekly_reminder_sent_on.is_(None))
            | (UserProfile.weekly_reminder_sent_on < local_date),
        )
    )
    return list(result.scalars())


async def _claim(session: AsyncSession, user_sub: str) -> date | None:
    """Take the right to send today's reminder, or return None because someone else has.

    This is the entire multi-replica story. The UPDATE's WHERE clause is evaluated by
    Postgres against the current row, so of N replicas racing on the same user exactly
    one matches and the rest update nothing.
    """
    local_date = cast(func.timezone(func.coalesce(UserProfile.timezone, "UTC"), func.now()), Date)
    result = await session.execute(
        update(UserProfile)
        .where(
            UserProfile.user_id == user_sub,
            (UserProfile.weekly_reminder_sent_on.is_(None))
            | (UserProfile.weekly_reminder_sent_on < local_date),
        )
        .values(weekly_reminder_sent_on=local_date)
        .returning(UserProfile.weekly_reminder_sent_on)
    )
    return result.scalar_one_or_none()


async def subscribe(
    session: AsyncSession, user_sub: str, *, endpoint: str, p256dh: str, auth: str
) -> None:
    """Record a browser's push subscription, keyed on its endpoint.

    An upsert, because a browser that re-subscribes (permission re-granted, service
    worker updated) hands back the same endpoint with fresh keys. Re-pointing it at the
    current user also matters on a shared device: the endpoint belongs to the browser,
    not the account, so the last person to enable notifications owns it.
    """
    await session.execute(
        insert(PushSubscription)
        .values(user_id=user_sub, endpoint=endpoint, p256dh=p256dh, auth=auth)
        .on_conflict_do_update(
            constraint="uq_push_subscriptions_endpoint",
            set_={"user_id": user_sub, "p256dh": p256dh, "auth": auth},
        )
    )
    await session.flush()


async def unsubscribe(session: AsyncSession, user_sub: str, *, endpoint: str) -> None:
    await session.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == user_sub, PushSubscription.endpoint == endpoint
        )
    )
    await session.flush()


async def get_settings_for(session: AsyncSession, user_sub: str) -> ReminderSettings:
    profile = await profile_service.get_or_create_profile(session, user_sub)
    devices = await session.execute(
        select(func.count(PushSubscription.id)).where(PushSubscription.user_id == user_sub)
    )
    return ReminderSettings(
        enabled=profile.weekly_reminder_hour is not None,
        hour=profile.weekly_reminder_hour,
        subscribed_devices=devices.scalar_one(),
    )


async def set_reminder(
    session: AsyncSession, user_sub: str, *, enabled: bool, hour: int | None = None
) -> ReminderSettings:
    """Turn the weekly reminder on or off, and pick the local hour it arrives.

    Turning it on clears `sent_on`: someone who enables it on a Sunday evening means
    *this* Sunday, and a stale date from a previous stint would swallow the first one
    silently.
    """
    if enabled and hour is not None and not 0 <= hour <= 23:
        raise ValueError("Reminder hour must be between 0 and 23.")

    profile = await profile_service.get_or_create_profile(session, user_sub)
    profile.weekly_reminder_hour = (
        (hour if hour is not None else DEFAULT_REMINDER_HOUR) if enabled else None
    )
    if enabled:
        profile.weekly_reminder_sent_on = None
    await session.flush()
    return await get_settings_for(session, user_sub)


async def _push(subscription: PushSubscription, *, title: str, body: str, url: str) -> bool:
    """One device. Returns False if the subscription is dead and should be dropped."""
    settings = get_settings()
    try:
        # `webpush` is `requests` underneath — blocking, and a push service that hangs
        # would otherwise stall the whole event loop, web requests included.
        await asyncio.to_thread(
            webpush,
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            ttl=PUSH_TTL_SECONDS,
        )
        return True
    except WebPushException as exc:
        # 404/410 is the push service saying this endpoint is permanently gone — the app
        # was uninstalled, or the browser rotated it. Anything else (timeout, 5xx) is
        # transient and the row stays: dropping it would silently unsubscribe someone
        # because a push service had a bad minute.
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            return False
        log.warning("push to %s failed: %s", subscription.id, exc)
        return True


async def send_reminder_to(session: AsyncSession, user_sub: str) -> int:
    """Send this user's reminder to every device they've subscribed. Returns how many
    were delivered. Assumes the claim has already been taken."""
    subscriptions = (
        (
            await session.execute(
                select(PushSubscription).where(PushSubscription.user_id == user_sub)
            )
        )
        .scalars()
        .all()
    )
    if not subscriptions:
        return 0

    # The body is the check-in's own summary rather than "time to check in": a
    # notification that already tells you something ("2 notes to pick up") is one you act
    # on, and it costs a read we already know how to do.
    checkin = await weekly_checkin.get_weekly_checkin(session, user_sub)
    delivered = 0
    for subscription in subscriptions:
        if await _push(subscription, title="Plan your week", body=checkin.summary, url="/plan"):
            delivered += 1
        else:
            await session.delete(subscription)
    await session.flush()
    return delivered


async def claim_and_send(session: AsyncSession, user_sub: str) -> bool:
    """One user's turn: take the claim, and send if it was ours to take.

    Claim and send share a transaction, and this never commits — the caller owns that,
    the same as every other service here. `reminder_loop` gives each user its own
    session, so committing at that boundary is what provides both the exactly-once
    guarantee and the isolation between users.
    """
    if not get_settings().push_enabled:
        return False
    if await _claim(session, user_sub) is None:
        return False  # another replica got there first
    await send_reminder_to(session, user_sub)
    return True


# Kept for the health/debug path: a one-line description of whether push can work at all.
def push_status() -> str:
    return "configured" if get_settings().push_enabled else "disabled (no VAPID keys)"


__all__ = [
    "DEFAULT_REMINDER_HOUR",
    "REMINDER_WEEKDAY",
    "ReminderSettings",
    "get_settings_for",
    "claim_and_send",
    "due_user_ids",
    "push_status",
    "send_reminder_to",
    "set_reminder",
    "subscribe",
    "unsubscribe",
]
