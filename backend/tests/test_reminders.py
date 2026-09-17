"""The weekly reminder.

Two things here are worth real tests and the rest is plumbing: the query that decides
whose local clock has reached their hour, and the claim that decides which replica gets
to send. Everything else — subscribe, settings, the router — is thin enough that its
tests are there to catch typos.

Nothing sends. `_push` is the only code that talks to a push service, and it's stubbed
wherever a test reaches it; these assert on who *would* be notified, which is the part
that can be wrong in an interesting way.
"""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.profile import UserProfile
from app.models.push import PushSubscription
from app.services import profile as profile_service
from app.services import reminders as service
from tests.conftest import OTHER_USER, TEST_USER

SUBSCRIPTION = {
    "endpoint": "https://push.example.com/abc",
    "p256dh": "BPtestkeytestkeytestkey",
    "auth": "authsecret",
}


@pytest.fixture
def push_configured(monkeypatch: pytest.MonkeyPatch):
    """Turn push on for one test. The suite runs with VAPID cleared (see conftest), so
    anything exercising the configured path has to say so."""
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "test-public-key")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-private-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _profile(session: AsyncSession, user: str, **fields) -> UserProfile:
    profile = await profile_service.get_or_create_profile(session, user)
    for name, value in fields.items():
        setattr(profile, name, value)
    await session.flush()
    return profile


# --- the claim: the whole multi-replica story ---------------------------------


async def test_claim_succeeds_once_and_then_refuses(session: AsyncSession) -> None:
    """Two replicas tick at the same minute. The second must come back empty rather than
    send a duplicate — this conditional UPDATE is what replaces a deliveries table."""
    await _profile(session, TEST_USER, weekly_reminder_hour=18, timezone="UTC")

    first = await service._claim(session, TEST_USER)
    second = await service._claim(session, TEST_USER)

    assert first is not None
    assert second is None


async def test_claim_is_per_user(session: AsyncSession) -> None:
    await _profile(session, TEST_USER, weekly_reminder_hour=18, timezone="UTC")
    await _profile(session, OTHER_USER, weekly_reminder_hour=18, timezone="UTC")

    assert await service._claim(session, TEST_USER) is not None
    assert await service._claim(session, OTHER_USER) is not None


async def test_claim_frees_up_on_a_later_date(session: AsyncSession) -> None:
    """Yesterday's claim must not swallow today's reminder."""
    await _profile(
        session,
        TEST_USER,
        weekly_reminder_hour=18,
        timezone="UTC",
        weekly_reminder_sent_on=date.today() - timedelta(days=1),
    )

    assert await service._claim(session, TEST_USER) is not None


async def test_claim_records_the_users_local_date_not_the_servers(
    session: AsyncSession,
) -> None:
    """Somewhere far enough east, "today" is already tomorrow in UTC. The stored date has
    to be the one the user is living in, or the lock releases a day early or late."""
    await _profile(session, TEST_USER, weekly_reminder_hour=18, timezone="Pacific/Kiritimati")

    claimed = await service._claim(session, TEST_USER)

    profile = await profile_service.get_or_create_profile(session, TEST_USER)
    assert claimed == profile.weekly_reminder_sent_on


# --- the due query ------------------------------------------------------------


async def test_nobody_is_due_without_a_reminder_hour(session: AsyncSession) -> None:
    await _profile(session, TEST_USER, weekly_reminder_hour=None, timezone="UTC")

    assert TEST_USER not in await service.due_user_ids(session)


async def test_due_matches_the_users_own_hour_in_their_own_zone(
    session: AsyncSession,
) -> None:
    """The point of the whole feature: "Sunday evening" is a different instant for every
    user, so this asks Postgres for the ones whose local clock reads their hour right
    now. Pinned by asking for whatever the current local weekday/hour happens to be, so
    the test doesn't depend on when it runs."""
    zone = "America/Los_Angeles"
    profile = await _profile(session, TEST_USER, timezone=zone)
    local_dow, local_hour = (
        await session.execute(
            select(
                service._local_now(UserProfile.timezone, "dow"),
                service._local_now(UserProfile.timezone, "hour"),
            ).where(UserProfile.user_id == TEST_USER)
        )
    ).one()
    profile.weekly_reminder_hour = int(local_hour)
    await session.flush()

    # Postgres counts Sunday as 0; `date.weekday()` counts it as 6.
    weekday = (int(local_dow) - 1) % 7
    due = await service.due_user_ids(session, weekday=weekday)

    assert TEST_USER in due
    assert TEST_USER not in await service.due_user_ids(session, weekday=(weekday + 1) % 7)


async def test_an_hour_off_is_not_due(session: AsyncSession) -> None:
    zone = "America/Los_Angeles"
    profile = await _profile(session, TEST_USER, timezone=zone)
    local_dow, local_hour = (
        await session.execute(
            select(
                service._local_now(UserProfile.timezone, "dow"),
                service._local_now(UserProfile.timezone, "hour"),
            ).where(UserProfile.user_id == TEST_USER)
        )
    ).one()
    profile.weekly_reminder_hour = (int(local_hour) + 1) % 24
    await session.flush()

    weekday = (int(local_dow) - 1) % 7
    assert TEST_USER not in await service.due_user_ids(session, weekday=weekday)


# --- subscriptions ------------------------------------------------------------


async def test_subscribing_twice_from_one_browser_updates_rather_than_duplicates(
    session: AsyncSession,
) -> None:
    """A browser re-subscribing returns the same endpoint. Two rows would mean two copies
    of every notification on one device."""
    await service.subscribe(session, TEST_USER, **SUBSCRIPTION)
    await service.subscribe(session, TEST_USER, **{**SUBSCRIPTION, "auth": "rotated"})

    rows = (
        (
            await session.execute(
                select(PushSubscription).where(PushSubscription.user_id == TEST_USER)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].auth == "rotated"


async def test_the_same_browser_can_move_to_another_account(session: AsyncSession) -> None:
    """The endpoint belongs to the browser, not the account — on a shared device the
    last person to enable notifications owns it, rather than the first keeping it."""
    await service.subscribe(session, TEST_USER, **SUBSCRIPTION)
    await service.subscribe(session, OTHER_USER, **SUBSCRIPTION)

    rows = (await session.execute(select(PushSubscription))).scalars().all()
    assert [r.user_id for r in rows] == [OTHER_USER]


async def test_unsubscribe_only_removes_the_callers_own(session: AsyncSession) -> None:
    await service.subscribe(session, TEST_USER, **SUBSCRIPTION)

    await service.unsubscribe(session, OTHER_USER, endpoint=SUBSCRIPTION["endpoint"])
    assert (await service.get_settings_for(session, TEST_USER)).subscribed_devices == 1

    await service.unsubscribe(session, TEST_USER, endpoint=SUBSCRIPTION["endpoint"])
    assert (await service.get_settings_for(session, TEST_USER)).subscribed_devices == 0


# --- settings -----------------------------------------------------------------


async def test_enabling_clears_a_stale_sent_date(session: AsyncSession) -> None:
    """Enabling on a Sunday evening means *this* Sunday. A leftover date from a previous
    stint would silently swallow the first reminder."""
    await _profile(session, TEST_USER, weekly_reminder_sent_on=date.today())

    await service.set_reminder(session, TEST_USER, enabled=True)

    profile = await profile_service.get_or_create_profile(session, TEST_USER)
    assert profile.weekly_reminder_sent_on is None
    assert profile.weekly_reminder_hour == service.DEFAULT_REMINDER_HOUR


async def test_disabling_turns_the_hour_off(session: AsyncSession) -> None:
    await service.set_reminder(session, TEST_USER, enabled=True, hour=20)
    settings = await service.set_reminder(session, TEST_USER, enabled=False)

    assert settings.enabled is False
    assert settings.hour is None


@pytest.mark.parametrize("hour", [-1, 24])
async def test_an_impossible_hour_is_rejected(session: AsyncSession, hour: int) -> None:
    with pytest.raises(ValueError, match="between 0 and 23"):
        await service.set_reminder(session, TEST_USER, enabled=True, hour=hour)


# --- sending ------------------------------------------------------------------


async def test_nothing_is_sent_when_push_is_unconfigured(session: AsyncSession) -> None:
    """The local default. It must be a quiet no-op, not an error — the app runs fine
    without VAPID keys, the same way it runs fine without AuthKit."""
    await _profile(session, TEST_USER, weekly_reminder_hour=18, timezone="UTC")

    assert await service.claim_and_send(session, TEST_USER) is False


async def test_a_dead_subscription_is_dropped_and_a_flaky_one_is_kept(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """410 Gone means the app was uninstalled; anything else means a push service had a
    bad minute. Dropping on the second would silently unsubscribe people."""
    await service.subscribe(session, TEST_USER, **SUBSCRIPTION)
    await service.subscribe(
        session, TEST_USER, **{**SUBSCRIPTION, "endpoint": "https://push.example.com/live"}
    )

    async def fake_push(subscription, **_: object) -> bool:
        return subscription.endpoint.endswith("live")

    monkeypatch.setattr(service, "_push", fake_push)
    await service.send_reminder_to(session, TEST_USER)

    remaining = (
        (
            await session.execute(
                select(PushSubscription.endpoint).where(PushSubscription.user_id == TEST_USER)
            )
        )
        .scalars()
        .all()
    )
    assert remaining == ["https://push.example.com/live"]


async def test_the_notification_body_is_the_checkin_summary(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reminder that already says something ("2 notes to pick up") gets acted on; "time
    to check in" gets swiped away."""
    await service.subscribe(session, TEST_USER, **SUBSCRIPTION)
    sent: dict[str, str] = {}

    async def fake_push(subscription, *, title: str, body: str, url: str) -> bool:
        sent.update(title=title, body=body, url=url)
        return True

    monkeypatch.setattr(service, "_push", fake_push)
    await service.send_reminder_to(session, TEST_USER)

    assert sent["url"] == "/plan"
    assert "sessions" in sent["body"], sent["body"]


# --- over REST ----------------------------------------------------------------


async def test_push_config_reports_disabled_without_keys(client: AsyncClient) -> None:
    resp = await client.get("/api/reminders/config")

    assert resp.status_code == 200
    assert resp.json() == {"enabled": False, "public_key": None}


async def test_subscribing_without_keys_configured_is_refused(client: AsyncClient) -> None:
    """A 503 rather than storing a subscription nothing will ever send to."""
    resp = await client.post(
        "/api/reminders/subscriptions",
        json={"endpoint": SUBSCRIPTION["endpoint"], "keys": {"p256dh": "x", "auth": "y"}},
    )

    assert resp.status_code == 503


async def test_reminder_settings_round_trip_over_rest(client: AsyncClient) -> None:
    resp = await client.put("/api/reminders", json={"enabled": True, "hour": 19})
    assert resp.status_code == 200
    assert resp.json() == {"enabled": True, "hour": 19, "subscribed_devices": 0}

    assert (await client.get("/api/reminders")).json()["hour"] == 19


async def test_rest_rejects_an_impossible_hour(client: AsyncClient) -> None:
    resp = await client.put("/api/reminders", json={"enabled": True, "hour": 25})

    assert resp.status_code == 422


async def test_claim_and_send_notifies_once_then_declines(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, push_configured: None
) -> None:
    """Claim and send together, which is what `reminder_loop.tick` calls per user. The
    second call is the 15-minute ticker coming round again inside the same local hour —
    it must stay quiet."""
    await _profile(session, TEST_USER, weekly_reminder_hour=18, timezone="UTC")
    await service.subscribe(session, TEST_USER, **SUBSCRIPTION)
    sends: list[str] = []

    async def fake_push(subscription, **_: object) -> bool:
        sends.append(subscription.endpoint)
        return True

    monkeypatch.setattr(service, "_push", fake_push)

    assert await service.claim_and_send(session, TEST_USER) is True
    assert sends == [SUBSCRIPTION["endpoint"]]

    assert await service.claim_and_send(session, TEST_USER) is False
    assert len(sends) == 1


async def test_due_weekday_is_read_at_call_time(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guards a subtle one: as a default argument, REMINDER_WEEKDAY would bind at import
    and the constant would look configurable while being anything but."""
    profile = await _profile(session, TEST_USER, timezone="UTC")
    local_dow, local_hour = (
        await session.execute(
            select(
                service._local_now(UserProfile.timezone, "dow"),
                service._local_now(UserProfile.timezone, "hour"),
            ).where(UserProfile.user_id == TEST_USER)
        )
    ).one()
    profile.weekly_reminder_hour = int(local_hour)
    await session.flush()

    monkeypatch.setattr(service, "REMINDER_WEEKDAY", (int(local_dow) - 1) % 7)
    assert TEST_USER in await service.due_user_ids(session)

    monkeypatch.setattr(service, "REMINDER_WEEKDAY", (int(local_dow) + 1) % 7)
    assert TEST_USER not in await service.due_user_ids(session)
