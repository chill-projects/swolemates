import dataclasses
import logging
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.partner import InviteStatus, PartnerInvite, Partnership, PartnershipMember
from app.schemas.partner import PartnerSummaryOut
from app.services import nutrition as nutrition_service
from app.services import partner as service
from app.services.errors import NotFoundError
from tests.conftest import OTHER_USER, TEST_USER


async def test_generate_invite_creates_a_pending_code(session: AsyncSession) -> None:
    invite = await service.generate_invite(session, TEST_USER)

    assert invite.inviter_id == TEST_USER
    assert invite.status == InviteStatus.pending
    assert len(invite.code) == 8
    assert invite.expires_at > datetime.now(UTC) + timedelta(days=6)


async def test_generate_invite_reuses_an_existing_pending_invite(session: AsyncSession) -> None:
    first = await service.generate_invite(session, TEST_USER)
    second = await service.generate_invite(session, TEST_USER)

    assert first.id == second.id
    assert first.code == second.code


async def test_generate_invite_rejects_an_already_linked_user(session: AsyncSession) -> None:
    invite = await service.generate_invite(session, TEST_USER)
    await service.redeem_invite(session, OTHER_USER, invite.code)

    try:
        await service.generate_invite(session, TEST_USER)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "already have a partner" in str(exc)


async def test_redeem_invite_links_both_users_ordered(session: AsyncSession) -> None:
    invite = await service.generate_invite(session, TEST_USER)

    partner_id = await service.redeem_invite(session, OTHER_USER, invite.code)

    assert partner_id == TEST_USER
    assert await service.get_partner_user_id(session, TEST_USER) == OTHER_USER
    assert await service.get_partner_user_id(session, OTHER_USER) == TEST_USER


async def test_redeem_invite_rejects_self_invite(session: AsyncSession) -> None:
    invite = await service.generate_invite(session, TEST_USER)

    try:
        await service.redeem_invite(session, TEST_USER, invite.code)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "your own invite" in str(exc)


async def test_redeem_invite_rejects_unknown_code(session: AsyncSession) -> None:
    try:
        await service.redeem_invite(session, OTHER_USER, "no-such-code")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "not found" in str(exc)


async def test_redeem_invite_rejects_an_already_redeemed_code(session: AsyncSession) -> None:
    invite = await service.generate_invite(session, TEST_USER)
    await service.redeem_invite(session, OTHER_USER, invite.code)

    third_user = "test_user_carol"
    try:
        await service.redeem_invite(session, third_user, invite.code)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "already been used" in str(exc)


async def test_redeem_invite_rejects_an_already_linked_redeemer(session: AsyncSession) -> None:
    first_invite = await service.generate_invite(session, TEST_USER)
    await service.redeem_invite(session, OTHER_USER, first_invite.code)

    third_user = "test_user_carol"
    second_invite = await service.generate_invite(session, third_user)
    try:
        await service.redeem_invite(session, OTHER_USER, second_invite.code)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "already have a partner" in str(exc)


async def test_redeem_invite_expires_a_stale_pending_invite(session: AsyncSession) -> None:
    session.add(
        PartnerInvite(
            inviter_id=TEST_USER,
            code="deadbeef",
            status=InviteStatus.pending,
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
    )
    await session.flush()

    try:
        await service.redeem_invite(session, OTHER_USER, "deadbeef")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "expired" in str(exc)

    result = await session.execute(select(PartnerInvite).where(PartnerInvite.code == "deadbeef"))
    invite = result.scalar_one()
    assert invite.status == InviteStatus.expired


async def test_invite_preview_valid_code_shows_inviter_name(session: AsyncSession) -> None:
    from app.services import profile as profile_service

    await profile_service.sync_display_name(session, TEST_USER, "Alice Example")
    invite = await service.generate_invite(session, TEST_USER)

    name, valid = await service.get_invite_preview(session, invite.code)

    assert valid is True
    assert name == "Alice Example"


async def test_invite_preview_missing_code_is_invalid_not_an_error(session: AsyncSession) -> None:
    name, valid = await service.get_invite_preview(session, "nope-nope")

    assert (name, valid) == (None, False)


async def test_invite_preview_redeemed_code_is_invalid(session: AsyncSession) -> None:
    invite = await service.generate_invite(session, TEST_USER)
    await service.redeem_invite(session, OTHER_USER, invite.code)

    name, valid = await service.get_invite_preview(session, invite.code)

    assert (name, valid) == (None, False)


async def test_get_partner_user_id_none_when_unlinked(session: AsyncSession) -> None:
    assert await service.get_partner_user_id(session, TEST_USER) is None


async def test_get_partner_summary_rejects_an_unlinked_target(session: AsyncSession) -> None:
    try:
        await service.get_partner_summary(session, TEST_USER, OTHER_USER)
        raise AssertionError("expected NotFoundError")
    except NotFoundError:
        pass


async def test_partner_summary_has_no_path_to_food_logs_or_weight(session: AsyncSession) -> None:
    """#12, resolved: the privacy boundary is a narrow return type, not RLS. This
    proves it structurally — seed the partner with real food logs and a weight entry,
    then assert neither the service dataclass nor the API schema has any field that
    data could travel through, not just that the response happens to omit it."""
    invite = await service.generate_invite(session, TEST_USER)
    await service.redeem_invite(session, OTHER_USER, invite.code)

    await nutrition_service.log_nutrition(
        session,
        OTHER_USER,
        entries=[{"trackable_key": "calories", "value": 2500}],
        name="a very specific cheat meal",
    )
    await nutrition_service.log_nutrition(
        session, OTHER_USER, entries=[{"trackable_key": "weight_lbs", "value": 181.4}]
    )
    await session.flush()

    summary = await service.get_partner_summary(session, TEST_USER, OTHER_USER)

    service_fields = {f.name for f in dataclasses.fields(summary)}
    assert service_fields == {
        "partner_user_sub",
        "partner_display_name",
        "streak",
        "frequency",
        "nutrition_streak",
        "personal_records",
    }
    assert not any("food" in f or "weight" in f or "log" in f for f in service_fields)

    schema_fields = set(PartnerSummaryOut.model_fields.keys())
    assert not any("food" in f or "weight" in f or "log" in f for f in schema_fields)


async def test_get_partner_summary_aggregates_are_scoped_to_the_partner(
    session: AsyncSession,
) -> None:
    invite = await service.generate_invite(session, TEST_USER)
    await service.redeem_invite(session, OTHER_USER, invite.code)

    await nutrition_service.log_nutrition(
        session, OTHER_USER, entries=[{"trackable_key": "calories", "value": 2000}]
    )
    await session.flush()

    summary = await service.get_partner_summary(session, TEST_USER, OTHER_USER)

    assert summary.partner_user_sub == OTHER_USER
    assert summary.nutrition_streak == 1
    assert summary.personal_records == []
    assert summary.frequency.total_workouts == 0


async def test_invite_preview_endpoint_is_unauthenticated(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The `client` fixture always authenticates as TEST_USER at the dependency-
    override level, so this doesn't prove *no* token works — that's guaranteed by
    construction, since the route declares no CurrentUser/CurrentPrincipal parameter
    for FastAPI to invoke. This proves the route + schema round-trip end to end."""
    invite = await service.generate_invite(session, TEST_USER)

    resp = await client.get(f"/api/partner/invite/{invite.code}")

    assert resp.status_code == 200
    assert resp.json()["valid"] is True


async def test_get_partner_endpoint_returns_null_when_unlinked(client: AsyncClient) -> None:
    resp = await client.get("/api/partner")

    assert resp.status_code == 200
    assert resp.json() is None


async def test_get_partner_user_id_degrades_instead_of_500ing_on_two_memberships(
    session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    """#40's real cost was that the corruption was *permanent*: `scalar_one_or_none()`
    turned a second membership row into a `MultipleResultsFound` on every subsequent
    partner request, so all three endpoints 500'd for that account until someone
    deleted a row by hand.

    `UNIQUE(user_id)` now makes two rows unreachable through the app, which is also why
    reaching the state at all takes dropping the constraint — done inside the test's own
    transaction, which Postgres rolls back along with everything else.
    """
    await session.execute(
        text("ALTER TABLE partnership_members DROP CONSTRAINT uq_partnership_members_user_id")
    )
    older, newer = Partnership(), Partnership()
    session.add_all([older, newer])
    await session.flush()
    # Explicit stamps, not the server default: `now()` is the *transaction* timestamp in
    # Postgres, so rows written together are indistinguishable and "oldest" would come
    # down to a random UUID tiebreak. A real race writes them from separate
    # transactions, seconds or days apart; this reproduces that, not the flush.
    then = datetime.now(UTC) - timedelta(days=2)
    session.add_all(
        [
            PartnershipMember(partnership_id=older.id, user_id=TEST_USER, created_at=then),
            PartnershipMember(partnership_id=older.id, user_id=OTHER_USER, created_at=then),
            PartnershipMember(partnership_id=newer.id, user_id=TEST_USER),
            PartnershipMember(partnership_id=newer.id, user_id="third_wheel"),
        ]
    )
    await session.flush()

    with caplog.at_level(logging.WARNING, logger="app.services.partner"):
        partner = await service.get_partner_user_id(session, TEST_USER)

    assert partner == OTHER_USER, "the older partnership wins"
    assert "more than one partnership" in caplog.text


async def test_get_partner_summary_rejects_someone_elses_partner(session: AsyncSession) -> None:
    """The privacy boundary (#12) has to reject a target who *is* partnered, just not
    with the caller — not merely one who's partnered with nobody. Reading membership
    without scoping to the caller's own partnership would let anyone name any linked
    user and read their aggregates."""
    invite = await service.generate_invite(session, TEST_USER)
    await service.redeem_invite(session, OTHER_USER, invite.code)

    stranger, their_partner = "stranger_one", "stranger_two"
    theirs = Partnership()
    session.add(theirs)
    await session.flush()
    session.add_all(
        [
            PartnershipMember(partnership_id=theirs.id, user_id=stranger),
            PartnershipMember(partnership_id=theirs.id, user_id=their_partner),
        ]
    )
    await session.flush()

    try:
        await service.get_partner_summary(session, TEST_USER, stranger)
        raise AssertionError("expected NotFoundError")
    except NotFoundError:
        pass
