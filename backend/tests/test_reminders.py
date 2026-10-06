"""The weekly reminder.

Two things here are worth real tests and the rest is plumbing: the query that decides
whose local clock has reached their hour, and the claim that decides which replica gets
to send. Everything else — subscribe, settings, the router — is thin enough that its
tests are there to catch typos.

Nothing sends. `_push` is the only code that talks to a push service, and it's stubbed
wherever a test reaches it; these assert on who *would* be notified, which is the part
that can be wrong in an interesting way.
"""

import asyncio
from datetime import date, timedelta

import pytest
import requests
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import reminder_loop
from app.config import get_settings
from app.models.profile import UserProfile
from app.models.push import PushSubscription
from app.services import profile as profile_service
from app.services import reminders as service
from tests.conftest import OTHER_USER, TEST_USER

SUBSCRIPTION = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
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
        session,
        TEST_USER,
        **{**SUBSCRIPTION, "endpoint": "https://fcm.googleapis.com/fcm/send/live"},
    )

    async def fake_push(subscription, **_: object) -> service.PushResult:
        if subscription.endpoint.endswith("live"):
            return service.PushResult.DELIVERED
        return service.PushResult.GONE

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
    assert remaining == ["https://fcm.googleapis.com/fcm/send/live"]


async def test_the_notification_body_is_the_checkin_summary(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reminder that already says something ("2 notes to pick up") gets acted on; "time
    to check in" gets swiped away."""
    await service.subscribe(session, TEST_USER, **SUBSCRIPTION)
    sent: dict[str, str] = {}

    async def fake_push(subscription, *, title: str, body: str, url: str) -> service.PushResult:
        sent.update(title=title, body=body, url=url)
        return service.PushResult.DELIVERED

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

    async def fake_push(subscription, **_: object) -> service.PushResult:
        sends.append(subscription.endpoint)
        return service.PushResult.DELIVERED

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


# --- review hardening -----------------------------------------------------------


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://fcm.googleapis.com/fcm/send/abc",
        "https://updates.push.services.mozilla.com/wpush/v2/abc",
        "https://wns2-par02p.notify.windows.com/w/?token=abc",
        "https://web.push.apple.com/QGx0abc",
    ],
)
def test_real_push_services_are_accepted(endpoint: str) -> None:
    assert service.validate_endpoint(endpoint) == endpoint


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/abc",  # not https
        "https://169.254.169.254/latest/meta-data/",
        "https://localhost/abc",
        "https://fcm.googleapis.com.evil.example/abc",
        "https://evilnotify.windows.com/abc",  # a suffix must start at a label
        "https://fcm.googleapis.com:8443/abc",
        "https://user@fcm.googleapis.com/abc",
        "not a url",
        "",
    ],
)
async def test_non_push_endpoints_are_refused(session: AsyncSession, endpoint: str) -> None:
    """The server POSTs to whatever is stored, so an arbitrary URL here is an SSRF."""
    with pytest.raises(service.InvalidPushEndpoint):
        await service.subscribe(session, TEST_USER, **{**SUBSCRIPTION, "endpoint": endpoint})
    assert (await service.get_settings_for(session, TEST_USER)).subscribed_devices == 0


async def test_rest_refuses_a_non_push_endpoint(client: AsyncClient, push_configured: None) -> None:
    resp = await client.post(
        "/api/reminders/subscriptions",
        json={"endpoint": "http://localhost:5432/", "keys": {"p256dh": "x", "auth": "y"}},
    )

    assert resp.status_code == 400


async def test_a_reassigned_endpoint_is_invisible_to_its_previous_owner(
    session: AsyncSession,
) -> None:
    """After the browser moves to B, A neither counts it nor can delete it."""
    await service.subscribe(session, TEST_USER, **SUBSCRIPTION)
    await service.subscribe(session, OTHER_USER, **SUBSCRIPTION)

    assert (await service.get_settings_for(session, TEST_USER)).subscribed_devices == 0
    await service.unsubscribe(session, TEST_USER, endpoint=SUBSCRIPTION["endpoint"])
    assert (await service.get_settings_for(session, OTHER_USER)).subscribed_devices == 1


async def test_one_unrecognised_timezone_does_not_break_the_due_query(
    session: AsyncSession,
) -> None:
    """Postgres's tz database isn't Python's. One name it doesn't know used to make the
    whole due query raise, so nobody got a reminder."""
    await _profile(session, OTHER_USER, weekly_reminder_hour=0, timezone="Mars/Olympus_Mons")
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

    assert TEST_USER in await service.due_user_ids(session, weekday=(int(local_dow) - 1) % 7)
    # The bad-zone user falls back to UTC rather than raising.
    assert await service._claim(session, OTHER_USER) is not None


async def test_push_uses_a_bounded_timeout(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, push_configured: None
) -> None:
    await service.subscribe(session, TEST_USER, **SUBSCRIPTION)
    subscription = (await session.execute(select(PushSubscription))).scalars().one()
    seen: dict[str, object] = {}

    def fake_webpush(**kwargs: object) -> None:
        seen.update(kwargs)

    monkeypatch.setattr(service, "webpush", fake_webpush)
    result = await service._push(subscription, title="t", body="b", url="/plan")

    assert result is service.PushResult.DELIVERED
    assert seen["timeout"] == service.PUSH_TIMEOUT_SECONDS


async def test_a_network_error_keeps_the_claim_and_the_subscription(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, push_configured: None
) -> None:
    """A ConnectionError used to escape claim_and_send, roll back the claim, and re-send
    to every device that had already received it on the next tick."""
    await _profile(session, TEST_USER, weekly_reminder_hour=18, timezone="UTC")
    await service.subscribe(session, TEST_USER, **SUBSCRIPTION)

    def flaky_webpush(**_: object) -> None:
        raise requests.ConnectionError("push service unreachable")

    monkeypatch.setattr(service, "webpush", flaky_webpush)

    assert await service.claim_and_send(session, TEST_USER) is False
    profile = await profile_service.get_or_create_profile(session, TEST_USER)
    assert profile.weekly_reminder_sent_on is not None
    assert (await service.get_settings_for(session, TEST_USER)).subscribed_devices == 1


async def test_claiming_with_no_devices_is_not_counted_as_notified(
    session: AsyncSession, push_configured: None
) -> None:
    await _profile(session, TEST_USER, weekly_reminder_hour=18, timezone="UTC")

    assert await service.claim_and_send(session, TEST_USER) is False


async def test_the_loop_ticks_before_its_first_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sleeping first would skip a reminder hour that starts just after a deploy."""
    calls: list[str] = []

    async def fake_tick() -> int:
        calls.append("tick")
        return 0

    async def fake_sleep(_: float) -> None:
        calls.append("sleep")
        raise asyncio.CancelledError

    monkeypatch.setattr(reminder_loop, "tick", fake_tick)
    monkeypatch.setattr(reminder_loop.asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await reminder_loop._tick_forever()

    assert calls == ["tick", "sleep"]
