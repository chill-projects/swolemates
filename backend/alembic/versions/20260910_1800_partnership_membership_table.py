"""partnerships + partnership_members, backfilled from partner_links

Revision ID: c7a13f5e6d84
Revises: a1c4e7f09b22
Create Date: 2026-09-10 18:00:00.000000

Blue-green note: additive-only. `partner_links` is left in place and still written by
the release this ships with, because the release *before* it reads `partner_links` to
decide whether someone already has a partner — dropping it here would let the old
version create a second link during the seconds both are serving. The drop is a
separate, later deploy.

#40. "A user has at most one partner" was enforced only by a Python check between a
SELECT and a flush, with nothing holding the rows in between, so two concurrent
redemptions could each pass every guard and both commit. Neither existing constraint
could catch it: `(Alice,Bob)` and `(Alice,Carol)` are two individually-valid rows of a
pair table, and the invariant spans rows. `UNIQUE(user_id)` on a membership table makes
it a per-row property Postgres enforces at any isolation level.

The backfill takes links oldest-first and skips any whose users are already members.
That matters because this bug may already have produced the corruption it prevents: a
user in two links can't become a member twice, and failing the migration would block
the deploy that fixes the bug. Oldest-first keeps the original partnership and drops
the later one that shouldn't have existed — the same choice a human would make cleaning
it up by hand. Any skipped link is reported in the migration log.
"""

import logging
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "c7a13f5e6d84"
down_revision: str | None = "a1c4e7f09b22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    op.create_table(
        "partnerships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_table(
        "partnership_members",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "partnership_id",
            UUID(as_uuid=True),
            sa.ForeignKey("partnerships.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("user_id", name="uq_partnership_members_user_id"),
    )

    _backfill(op.get_bind())


def _backfill(bind: sa.engine.Connection) -> None:
    links = bind.execute(
        sa.text(
            "SELECT id, user_id_a, user_id_b, created_at FROM partner_links ORDER BY created_at, id"
        )
    ).all()

    claimed: set[str] = set()
    skipped: list[tuple[str, str, str]] = []
    for link_id, user_id_a, user_id_b, created_at in links:
        if user_id_a in claimed or user_id_b in claimed:
            skipped.append((str(link_id), user_id_a, user_id_b))
            continue

        partnership_id = uuid.uuid4()
        bind.execute(
            sa.text("INSERT INTO partnerships (id, created_at) VALUES (:id, :created_at)"),
            {"id": partnership_id, "created_at": created_at},
        )
        bind.execute(
            sa.text(
                "INSERT INTO partnership_members (id, partnership_id, user_id, created_at)"
                " VALUES (:id, :partnership_id, :user_id, :created_at)"
            ),
            [
                {
                    "id": uuid.uuid4(),
                    "partnership_id": partnership_id,
                    "user_id": user_id,
                    "created_at": created_at,
                }
                for user_id in (user_id_a, user_id_b)
            ],
        )
        claimed.update((user_id_a, user_id_b))

    logger.info("partnerships backfill: %d link(s) migrated", len(links) - len(skipped))
    for link_id, user_id_a, user_id_b in skipped:
        # Loud on purpose: this is a partnership that existed in the old table and does
        # not exist in the new one. It can only appear if the race in #40 already fired.
        logger.warning(
            "partnerships backfill: skipped partner_links row %s (%s, %s) — "
            "a user in it already belongs to an earlier partnership",
            link_id,
            user_id_a,
            user_id_b,
        )


def downgrade() -> None:
    # partner_links was never touched on the way up, so it still holds every link the
    # backfill read. Nothing to restore.
    op.drop_table("partnership_members")
    op.drop_table("partnerships")
