"""The post-#41 reconcile migration (5b9e2d41c0a7), exercised directly.

The case it exists for: the release before #41 kept serving through the blue-green
overlap and wrote links to `partner_links` only, after the backfill had already run.
Those links have no membership rows, and every current read goes through membership.

It runs unattended against production, which is consistent apart from (at most) those
stragglers — so "does nothing on consistent data" matters as much as the fix itself.
Driven like test_partner_backfill.py: `run_sync` inside the rolled-back session.
"""

import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.partner import Partnership, PartnershipMember

MIGRATION = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "20261006_1500_reconcile_partner_links_stragglers.py"
)

ALICE, BOB, CAROL, DAVE = "recon_alice", "recon_bob", "recon_carol", "recon_dave"


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("reconcile_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _add_link(session: AsyncSession, one: str, two: str, *, created_at: datetime) -> None:
    user_id_a, user_id_b = sorted((one, two))
    await session.execute(
        text(
            "INSERT INTO partner_links (id, user_id_a, user_id_b, created_at)"
            " VALUES (:id, :a, :b, :created_at)"
        ),
        {"id": uuid.uuid4(), "a": user_id_a, "b": user_id_b, "created_at": created_at},
    )


async def _add_partnership(session: AsyncSession, one: str, two: str) -> uuid.UUID:
    """What the new release writes on redeem: a partnership and its two members (plus
    the dual-written link, added separately by the caller where it matters)."""
    partnership = Partnership()
    session.add(partnership)
    await session.flush()
    session.add_all(
        [
            PartnershipMember(partnership_id=partnership.id, user_id=one),
            PartnershipMember(partnership_id=partnership.id, user_id=two),
        ]
    )
    await session.flush()
    return partnership.id


async def _reconcile(session: AsyncSession) -> None:
    reconcile = _migration()._reconcile
    await session.run_sync(lambda sync_session: reconcile(sync_session.connection()))


async def _members(session: AsyncSession, user: str) -> list[uuid.UUID]:
    rows = await session.execute(
        select(PartnershipMember.partnership_id).where(PartnershipMember.user_id == user)
    )
    return list(rows.scalars())


async def _partnership_count(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(Partnership))).scalar_one()


async def test_a_link_written_only_by_the_old_release_gets_its_partnership(
    session: AsyncSession,
) -> None:
    await _add_link(session, ALICE, BOB, created_at=datetime.now(UTC))

    await _reconcile(session)

    alice, bob = await _members(session, ALICE), await _members(session, BOB)
    assert len(alice) == 1
    assert alice == bob


async def test_consistent_data_is_left_alone(session: AsyncSession) -> None:
    """The production case after the stragglers are fixed — and the case on every
    database that never saw the overlap. Must insert nothing."""
    partnership_id = await _add_partnership(session, ALICE, BOB)
    await _add_link(session, ALICE, BOB, created_at=datetime.now(UTC))
    before = await _partnership_count(session)

    await _reconcile(session)

    assert await _partnership_count(session) == before
    assert await _members(session, ALICE) == [partnership_id]
    assert await _members(session, BOB) == [partnership_id]


async def test_running_twice_is_a_no_op_the_second_time(session: AsyncSession) -> None:
    await _add_link(session, ALICE, BOB, created_at=datetime.now(UTC))
    await _reconcile(session)
    after_first = await _partnership_count(session)

    await _reconcile(session)

    assert await _partnership_count(session) == after_first
    assert len(await _members(session, ALICE)) == 1


async def test_a_straggler_clashing_with_an_existing_membership_is_skipped(
    session: AsyncSession,
) -> None:
    """Carol linked to Alice through the new release (membership exists); during the
    overlap the old release, reading only partner_links, also let Carol link to Dave.
    UNIQUE(user_id) can't hold both — the existing membership wins and Dave is left
    unlinked rather than the migration aborting the deploy."""
    first = datetime.now(UTC) - timedelta(days=1)
    partnership_id = await _add_partnership(session, ALICE, CAROL)
    await _add_link(session, ALICE, CAROL, created_at=first)
    await _add_link(session, CAROL, DAVE, created_at=first + timedelta(hours=1))

    await _reconcile(session)

    assert await _members(session, CAROL) == [partnership_id]
    assert await _members(session, DAVE) == []


async def test_two_stragglers_sharing_a_user_keep_the_older(session: AsyncSession) -> None:
    first = datetime.now(UTC) - timedelta(days=1)
    await _add_link(session, ALICE, BOB, created_at=first)
    await _add_link(session, BOB, CAROL, created_at=first + timedelta(hours=1))

    await _reconcile(session)

    bob = await _members(session, BOB)
    assert len(bob) == 1
    assert await _members(session, ALICE) == bob
    assert await _members(session, CAROL) == []
