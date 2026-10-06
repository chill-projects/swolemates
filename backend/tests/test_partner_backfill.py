"""The #40 migration's backfill, exercised directly.

It runs once, unattended, in Railway's pre-deploy step, against data this very bug may
already have corrupted — the one place where getting it wrong stops the fix from
shipping at all. So the interesting case isn't the happy path, it's a `partner_links`
table that already contains a user in two links: `UNIQUE(user_id)` cannot accept both,
and an unguarded insert would abort the migration and roll the deploy back.

Driven through `run_sync` because the migration takes a sync connection while the test
suite is async; the rolled-back `session` fixture then cleans up for free.
"""

import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.partner import PartnershipMember

MIGRATION = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "20260910_1800_partnership_membership_table.py"
)

ALICE, BOB, CAROL = "backfill_alice", "backfill_bob", "backfill_carol"


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("partnership_migration", MIGRATION)
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


async def _run_backfill(session: AsyncSession) -> None:
    backfill = _migration()._backfill
    await session.run_sync(lambda sync_session: backfill(sync_session.connection()))


async def _members(session: AsyncSession, user: str) -> list[uuid.UUID]:
    rows = await session.execute(
        select(PartnershipMember.partnership_id).where(PartnershipMember.user_id == user)
    )
    return list(rows.scalars())


async def test_backfill_carries_a_link_across_as_one_partnership(session: AsyncSession) -> None:
    await _add_link(session, ALICE, BOB, created_at=datetime.now(UTC))

    await _run_backfill(session)

    alice, bob = await _members(session, ALICE), await _members(session, BOB)
    assert len(alice) == 1
    assert alice == bob, "both sides of a link must land in the same partnership"


async def test_backfill_keeps_the_older_link_when_a_user_is_in_two(
    session: AsyncSession,
) -> None:
    """The corruption this migration exists to prevent may already be in the table.
    Alice was linked to Bob first; the link to Carol is the one the race shouldn't have
    allowed, so it's the one dropped — the same call a human would make by hand."""
    first = datetime.now(UTC) - timedelta(days=3)
    await _add_link(session, ALICE, BOB, created_at=first)
    await _add_link(session, ALICE, CAROL, created_at=first + timedelta(days=1))

    await _run_backfill(session)

    alice, bob = await _members(session, ALICE), await _members(session, BOB)
    assert len(alice) == 1, "the whole point of the new table is one membership per user"
    assert alice == bob
    assert await _members(session, CAROL) == [], "the later, racing link is dropped"


async def test_backfill_of_an_empty_table_is_a_no_op(session: AsyncSession) -> None:
    await _run_backfill(session)

    assert await _members(session, ALICE) == []
