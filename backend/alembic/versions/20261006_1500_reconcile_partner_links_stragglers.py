"""reconcile partner_links rows the #41 backfill never saw

Revision ID: 5b9e2d41c0a7
Revises: 937641e786e2
Create Date: 2026-10-06 15:00:00.000000

c7a13f5e6d84 backfilled `partnership_members` from `partner_links` in pre-deploy, but
the release before it kept serving for the blue-green overlap and wrote *only*
`partner_links`. Any link redeemed in that window has no membership rows, and every
read in the current code goes through membership — so for those two users the partner
feature reads as "not linked" while the old table says otherwise.

This re-runs the same reconciliation against whatever is in the tables now: links
oldest-first, a link is carried across only if neither user already belongs to a
partnership, and every link that can't be carried is logged. Rows that already agree
(both users members of one partnership) are the expected case and pass silently, so on
a consistent database this inserts nothing — it's safe to run against prod as-is, and
safe to run twice.

Additive only (inserts into tables the running release already reads and writes), so it
is fine under the blue-green overlap. Constraint names were checked while here: alembic
applies `target_metadata`'s naming convention to `op.create_table`, so c7a13f5e6d84
already produced `pk_partnerships`, `pk_partnership_members` and
`fk_partnership_members_partnership_id_partnerships` — nothing to rename.
"""

import logging
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5b9e2d41c0a7"
down_revision: str | None = "937641e786e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    _reconcile(op.get_bind())


def _reconcile(bind: sa.engine.Connection) -> None:
    membership: dict[str, uuid.UUID] = dict(
        bind.execute(sa.text("SELECT user_id, partnership_id FROM partnership_members")).all()
    )
    links = bind.execute(
        sa.text(
            "SELECT id, user_id_a, user_id_b, created_at FROM partner_links ORDER BY created_at, id"
        )
    ).all()

    migrated = 0
    skipped: list[tuple[str, str, str]] = []
    for link_id, user_id_a, user_id_b, created_at in links:
        in_a, in_b = membership.get(user_id_a), membership.get(user_id_b)
        if in_a is not None and in_a == in_b:
            continue  # already carried across — the normal case
        if in_a is not None or in_b is not None:
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
        membership[user_id_a] = membership[user_id_b] = partnership_id
        migrated += 1

    logger.info("partner_links reconcile: %d straggler link(s) migrated", migrated)
    for link_id, user_id_a, user_id_b in skipped:
        # Same as the original backfill: a link that exists in partner_links and has no
        # partnership. No release since #41 reads partner_links, so it is invisible to
        # users, but the partner_links drop must account for it — see docs/design.md §6.
        logger.warning(
            "partner_links reconcile: skipped partner_links row %s (%s, %s) — "
            "a user in it already belongs to another partnership",
            link_id,
            user_id_a,
            user_id_b,
        )


def downgrade() -> None:
    # Not reversible without guessing which partnerships this created, and the older
    # code it would downgrade to reads partner_links, which still holds every link.
    pass
