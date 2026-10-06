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
from enum import Enum
from urllib.parse import urlsplit

import requests
from pywebpush import WebPushException, webpush
from sqlalchemy import Date, case, cast, delete, func, literal_column, select, text, update
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

# Seconds to wait on a push service before giving up on that device. pywebpush forwards
# `timeout=None` to `requests` unless told otherwise, which means wait forever — and a
# worker thread stuck on one hung push service would hold that user's claim open forever.
PUSH_TIMEOUT_SECONDS = 10

# The server POSTs to whatever endpoint a browser registers, so the endpoint is an
# outbound-request target supplied by a client: unchecked, it's an SSRF primitive
# (`http://169.254.169.254/...`, `http://localhost:5432`). Only the real browser push
# services are accepted. Exact hosts, plus suffixes for services that shard by hostname.
#   Chrome/Chromium/Opera/Samsung: fcm.googleapis.com (legacy: android.googleapis.com)
#   Firefox: updates.push.services.mozilla.com
#   Edge (Windows): <shard>.notify.windows.com
#   Safari (macOS/iOS): web.push.apple.com
PUSH_HOSTS = frozenset(
    {
        "fcm.googleapis.com",
        "android.googleapis.com",
        "updates.push.services.mozilla.com",
        "web.push.apple.com",
    }
)
PUSH_HOST_SUFFIXES = (".push.services.mozilla.com", ".notify.windows.com", ".push.apple.com")


class InvalidPushEndpoint(ValueError):
    pass


def validate_endpoint(endpoint: str) -> str:
    """Return `endpoint` if it points at a known browser push service, else raise.

    Lives here, not in the schema or router, so it holds for any future caller of
    `subscribe` — the same reason permission checks live in services.
    """
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError as exc:
        raise InvalidPushEndpoint("That push endpoint isn't a valid URL.") from exc
    host = (parts.hostname or "").lower()
    if (
        parts.scheme != "https"
        or parts.username is not None
        or parts.password is not None
        or port not in (None, 443)
        or not (host in PUSH_HOSTS or host.endswith(PUSH_HOST_SUFFIXES))
    ):
        raise InvalidPushEndpoint("That push endpoint isn't from a recognised push service.")
    return endpoint


@dataclass
class ReminderSettings:
    enabled: bool
    hour: int | None
    subscribed_devices: int


def _zone(tz_column):
    """The user's zone as Postgres will accept it, or UTC.

    `profile.timezone` is validated against Python's zoneinfo when it's set, but
    Postgres ships its own tz database and the two can disagree (a newly added zone, a
    hand-edited row). An unrecognised name makes `timezone()` raise — and because the due
    query covers every user at once, one bad row would stop the reminder for everyone.
    Checking against `pg_timezone_names` contains that to the one user, who falls back
    to UTC like a user with no zone set.
    """
    known = select(literal_column("name")).select_from(text("pg_timezone_names"))
    return case((tz_column.in_(known.scalar_subquery()), tz_column), else_="UTC")


def _local_date():
    return cast(func.timezone(_zone(UserProfile.timezone), func.now()), Date)


def _local_now(tz_column, part: str):
    """`EXTRACT(part FROM now() AT TIME ZONE <the user's own zone>)`.

    Done in SQL rather than by pulling every profile into Python and looping: the set of
    users whose local clock currently reads Sunday 18:00 is a query, and writing it as
    one keeps the tick O(due users) instead of O(all users).
    """
    local = func.timezone(_zone(tz_column), func.now())
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
    local_date = _local_date()
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
    local_date = _local_date()
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

    That reassignment can't be abused to read someone else's notifications: a push is
    encrypted to the `p256dh`/`auth` keys stored with it, which only the browser that
    created the subscription holds. Posting another user's endpoint with your own keys
    just produces pushes that browser can't decrypt — and the endpoint itself is an
    unguessable capability URL. Reads and deletes stay filtered to the caller's rows.

    Raises `InvalidPushEndpoint` for anything that isn't a browser push service.
    """
    validate_endpoint(endpoint)
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


class PushResult(Enum):
    DELIVERED = "delivered"
    FAILED = "failed"  # transient: keep the subscription, try again next week
    GONE = "gone"  # the push service says this endpoint is dead: drop it


async def _push(subscription: PushSubscription, *, title: str, body: str, url: str) -> PushResult:
    """One device. Never raises: a failure here must not escape `claim_and_send`, or the
    claim rolls back and every device that *did* get the push gets it again next tick."""
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
            timeout=PUSH_TIMEOUT_SECONDS,
        )
        return PushResult.DELIVERED
    except WebPushException as exc:
        # 404/410 is the push service saying this endpoint is permanently gone — the app
        # was uninstalled, or the browser rotated it. Anything else (5xx, 429) is
        # transient and the row stays: dropping it would silently unsubscribe someone
        # because a push service had a bad minute.
        #
        # 401/403 deliberately aren't pruned. After a VAPID key rotation they do mean
        # "this subscription belongs to the old key", but they're also exactly what a
        # misconfigured key on *our* side returns, and pruning on that would unsubscribe
        # every user in one tick. The SPA notices a changed key and re-subscribes
        # (removing the stale row) instead.
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            return PushResult.GONE
        log.warning("push to %s failed: %s", subscription.id, exc)
        return PushResult.FAILED
    except requests.RequestException as exc:
        # Connection refused, DNS, the timeout above — the network, not the endpoint.
        log.warning("push to %s failed: %s", subscription.id, exc)
        return PushResult.FAILED
    except Exception:
        # Anything else (a malformed stored key, say) is still one device's problem.
        log.exception("push to %s failed", subscription.id)
        return PushResult.FAILED


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
        result = await _push(
            subscription, title="Plan your week", body=checkin.summary, url="/plan"
        )
        if result is PushResult.DELIVERED:
            delivered += 1
        elif result is PushResult.GONE:
            await session.delete(subscription)
    await session.flush()
    return delivered


async def claim_and_send(session: AsyncSession, user_sub: str) -> bool:
    """One user's turn: take the claim, and send if it was ours to take. True only if
    at least one device actually received it.

    Claim and send share a transaction, and this never commits — the caller owns that,
    the same as every other service here. `reminder_loop` gives each user its own
    session, so committing at that boundary is what provides both the exactly-once
    guarantee and the isolation between users.
    """
    if not get_settings().push_enabled:
        return False
    if await _claim(session, user_sub) is None:
        return False  # another replica got there first
    return await send_reminder_to(session, user_sub) > 0


# Kept for the health/debug path: a one-line description of whether push can work at all.
def push_status() -> str:
    return "configured" if get_settings().push_enabled else "disabled (no VAPID keys)"


__all__ = [
    "DEFAULT_REMINDER_HOUR",
    "InvalidPushEndpoint",
    "PushResult",
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
    "validate_endpoint",
]
