"""The two races from #40, run for real.

Everything else in the partner suite shares one rolled-back session, which by
construction cannot exhibit a race: a single transaction sees its own writes, so the
Python guards in `redeem_invite` always look correct there. That's exactly why the bug
survived a passing test suite. These tests open two real connections and commit on
both, so the interleaving is the database's rather than the ORM's.

Two coroutines under `asyncio.gather` are *not* enough on their own. The window here is
a Python comparison plus a round trip, and the first redemption usually runs to commit
before the second one starts — at which point the guard rejects it honestly and the
test passes without ever reaching the race. Written that way, two of these three passed
against deliberately unfixed code. So `race_at_the_guard` pins both transactions past
the already-linked check before either is allowed to write, which is the interleaving
the issue describes and the only one worth asserting on.

They clean up after themselves — they can't use the rolled-back `session` fixture and
have to leave the schema as they found it for whatever runs next.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

import psycopg.errors
import pytest
from sqlalchemy import delete, event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.partner import PartnerInvite, PartnerLink, Partnership, PartnershipMember
from app.models.profile import UserProfile
from app.services import partner as service

ALICE = "race_user_alice"
BOB = "race_user_bob"
CAROL = "race_user_carol"
DAVE = "race_user_dave"
EVERYONE = (ALICE, BOB, CAROL, DAVE)


@pytest.fixture
async def sessions(migrated_database: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A sessionmaker over real, separately-committing connections."""
    engine = create_async_engine(migrated_database, connect_args={"options": "-c timezone=utc"})
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield maker
    finally:
        async with maker() as cleanup:
            member_of = select(PartnershipMember.partnership_id).where(
                PartnershipMember.user_id.in_(EVERYONE)
            )
            await cleanup.execute(
                delete(Partnership).where(Partnership.id.in_(member_of.scalar_subquery()))
            )
            await cleanup.execute(
                delete(PartnershipMember).where(PartnershipMember.user_id.in_(EVERYONE))
            )
            await cleanup.execute(delete(PartnerLink).where(PartnerLink.user_id_a.in_(EVERYONE)))
            await cleanup.execute(
                delete(PartnerInvite).where(PartnerInvite.inviter_id.in_(EVERYONE))
            )
            await cleanup.execute(delete(UserProfile).where(UserProfile.user_id.in_(EVERYONE)))
            await cleanup.commit()
        await engine.dispose()


@pytest.fixture
def race_at_the_guard(monkeypatch: pytest.MonkeyPatch) -> Callable[[], None]:
    """Arms a gate that holds `redeem_invite` at the point the bug lives — just after
    it has read whether the caller already has a partner, and before it writes anything
    — until two redemptions are sitting there together. That is precisely the state the
    guards cannot detect, and the state real traffic reaches by chance.

    Armed by the test rather than by the fixture, because `generate_invite` consults the
    same guard: gating it from setup leaves the first invite waiting for a second party
    that never comes. `monkeypatch.undo()` lifts the gate for assertions made after the
    race.
    """

    def arm() -> None:
        barrier = asyncio.Barrier(2)
        real = service.get_partner_user_id

        async def gated(session: AsyncSession, user_sub: str) -> str | None:
            partner = await real(session, user_sub)
            await barrier.wait()
            return partner

        monkeypatch.setattr(service, "get_partner_user_id", gated)

    return arm


async def _invite_code(maker: async_sessionmaker[AsyncSession], inviter: str) -> str:
    async with maker() as s:
        invite = await service.generate_invite(s, inviter)
        code = invite.code
        await s.commit()
    return code


async def _redeem(maker: async_sessionmaker[AsyncSession], user: str, code: str) -> str | None:
    """Runs one redemption to completion on its own connection. Returns the partner's
    id on success, or None if it was rejected — a rejection is the *correct* outcome
    for whichever of two racing redemptions loses."""
    async with maker() as s:
        try:
            partner = await service.redeem_invite(s, user, code)
        except ValueError:
            await s.rollback()
            return None
        await s.commit()
        return partner


async def _redeem_error(maker: async_sessionmaker[AsyncSession], user: str, code: str) -> str:
    """Like `_redeem`, but keeps the rejection message instead of discarding it."""
    async with maker() as s:
        try:
            await service.redeem_invite(s, user, code)
        except ValueError as exc:
            await s.rollback()
            return str(exc)
        await s.commit()
        return ""


async def _partner_count(maker: async_sessionmaker[AsyncSession], user: str) -> int:
    async with maker() as s:
        rows = await s.execute(
            select(PartnershipMember.id).where(PartnershipMember.user_id == user)
        )
        return len(rows.all())


def _one_won(results: list[str | None]) -> None:
    assert sorted(r is None for r in results) == [False, True], (
        f"expected exactly one redemption to succeed, got {results}"
    )


async def _gather(*calls: Awaitable[str | None]) -> list[str | None]:
    return list(await asyncio.gather(*calls))


async def test_two_people_cannot_redeem_the_same_invite(
    sessions: async_sessionmaker[AsyncSession],
    race_at_the_guard: Callable[[], None],
) -> None:
    """Race 1. Invite codes are meant to be shared into a group chat, so two people
    tapping the same link at once is the expected usage, not an exotic case. Both used
    to read `pending`, both pass the guard, and both commit — leaving Alice linked to
    two people and every partner endpoint 500ing for her from then on."""
    code = await _invite_code(sessions, ALICE)
    race_at_the_guard()

    results = await _gather(_redeem(sessions, BOB, code), _redeem(sessions, CAROL, code))

    _one_won(results)
    assert await _partner_count(sessions, ALICE) == 1


async def test_one_person_cannot_redeem_two_invites_at_once(
    sessions: async_sessionmaker[AsyncSession],
    race_at_the_guard: Callable[[], None],
) -> None:
    """Race 2 — write skew. Bob holds codes from Alice and Dave. The two transactions
    write different invite rows and different partnership rows, so they collide on
    nothing and a row lock on the invite can't see them; `REPEATABLE READ` wouldn't
    either. Only `UNIQUE(user_id)` on the membership row catches this one."""
    from_alice = await _invite_code(sessions, ALICE)
    from_dave = await _invite_code(sessions, DAVE)
    race_at_the_guard()

    results = await _gather(_redeem(sessions, BOB, from_alice), _redeem(sessions, BOB, from_dave))

    _one_won(results)
    assert await _partner_count(sessions, BOB) == 1


async def test_the_loser_of_a_race_still_gets_a_usable_partner_view(
    sessions: async_sessionmaker[AsyncSession],
    race_at_the_guard: Callable[[], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The corruption's real cost was that it was permanent: two membership rows turned
    `scalar_one_or_none()` into a `MultipleResultsFound` on every later request, so the
    feature stayed dead for that account until someone deleted a row by hand. Whoever
    loses the race must still be able to read their own partner state."""
    code = await _invite_code(sessions, ALICE)
    race_at_the_guard()

    results = await _gather(_redeem(sessions, BOB, code), _redeem(sessions, CAROL, code))
    loser = BOB if results[0] is None else CAROL
    winner = CAROL if results[0] is None else BOB

    monkeypatch.undo()  # the barrier is spent; read partner state normally
    async with sessions() as s:
        assert await service.get_partner_user_id(s, loser) is None
        assert await service.get_partner_user_id(s, winner) == ALICE
        assert await service.get_partner_user_id(s, ALICE) == winner


async def test_the_second_redeemer_is_told_the_code_was_used(
    sessions: async_sessionmaker[AsyncSession],
    race_at_the_guard: Callable[[], None],
) -> None:
    """What the row lock buys, over and above the constraint.

    `UNIQUE(user_id)` alone already makes this race safe — with the lock removed, every
    other test here still passes. But then Carol loses on the *constraint*, and the only
    honest thing to say about an `IntegrityError` on her membership row is "you already
    have a partner linked" — which is false, and unactionable. Under the lock she
    serializes behind Bob, re-reads a `redeemed` invite, and gets the message the guard
    always meant for her.
    """
    code = await _invite_code(sessions, ALICE)
    race_at_the_guard()

    messages = list(
        await asyncio.gather(
            _redeem_error(sessions, BOB, code), _redeem_error(sessions, CAROL, code)
        )
    )

    assert sorted(messages) == ["", "This invite has already been used."]


async def test_mutual_redemption_rejects_one_cleanly_instead_of_deadlocking(
    sessions: async_sessionmaker[AsyncSession],
    race_at_the_guard: Callable[[], None],
) -> None:
    """Alice and Bob each send the other a code and both tap at once. The two
    transactions lock different invites, so nothing serializes them until the
    membership inserts — and inserted inviter-first, Alice's transaction took Bob's
    `user_id` slot while Bob's took Alice's, each then waiting on the other: a Postgres
    deadlock, raised as `OperationalError` (a 500), not the `IntegrityError` the
    redeem path handles. Inserting both members in `user_id` order means the loser
    blocks on the first slot, then fails on the constraint once the winner commits.

    Both rows go in one multi-row INSERT, so the deadlock window is microseconds and
    this rarely reproduces it even unfixed — it pins the clean outcome. The ordering
    itself is pinned deterministically by the next test."""
    from_alice = await _invite_code(sessions, ALICE)
    from_bob = await _invite_code(sessions, BOB)
    race_at_the_guard()

    messages = list(
        await asyncio.gather(
            _redeem_error(sessions, BOB, from_alice), _redeem_error(sessions, ALICE, from_bob)
        )
    )

    # The loser now *has* a partner — the winner's redemption linked them — so the
    # already-linked message is the true one here.
    assert sorted(messages) == ["", "You already have a partner linked."]
    assert await _partner_count(sessions, ALICE) == 1
    assert await _partner_count(sessions, BOB) == 1


async def test_redeeming_an_invite_whose_sender_has_since_linked_says_so(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Alice shared a code, then linked with Dave through Dave's code. Her own invite is
    still `pending`, so Bob passes every guard and fails on *Alice's* membership row.
    That used to tell Bob "You already have a partner linked." — and he doesn't."""
    from_alice = await _invite_code(sessions, ALICE)
    from_dave = await _invite_code(sessions, DAVE)
    assert await _redeem(sessions, ALICE, from_dave) == DAVE

    assert await _redeem_error(sessions, BOB, from_alice) == "This invite is no longer available."
    assert await _partner_count(sessions, BOB) == 0


async def test_members_are_inserted_in_user_id_order(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The deadlock fix, pinned without needing to win a microsecond race: Dave's code
    redeemed by Bob must still write Bob's membership row before Dave's."""
    from_dave = await _invite_code(sessions, DAVE)
    engine = sessions.kw["bind"].sync_engine
    order: list[str] = []

    def capture(_conn, _cursor, statement, parameters, _context, _executemany) -> None:  # noqa: ANN001
        if statement.lstrip().upper().startswith("INSERT INTO PARTNERSHIP_MEMBERS"):
            flat = parameters.values() if isinstance(parameters, dict) else parameters
            order.extend(v for v in flat if v in EVERYONE)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        assert await _redeem(sessions, BOB, from_dave) == DAVE
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert order == sorted([BOB, DAVE])


async def test_a_deadlock_is_reported_as_a_lost_race_not_a_500(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Belt and braces for the ordering above: if Postgres aborts the redemption with
    deadlock_detected anyway, the caller gets a ValueError (a 4xx), like any lost race."""
    from_alice = await _invite_code(sessions, ALICE)
    real_flush = AsyncSession.flush

    async def deadlocking_flush(self: AsyncSession, *args: object, **kwargs: object) -> None:
        if any(isinstance(obj, PartnershipMember) for obj in self.new):
            raise OperationalError("INSERT", {}, psycopg.errors.DeadlockDetected())
        await real_flush(self, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "flush", deadlocking_flush)

    assert await _redeem_error(sessions, BOB, from_alice) == "This invite is no longer available."
    monkeypatch.undo()
    assert await _partner_count(sessions, BOB) == 0
