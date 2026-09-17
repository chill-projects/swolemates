"""weekly reminder: push subscriptions + profile schedule

Revision ID: af364567dc8e
Revises: a1c4e7f09b22
Create Date: 2026-09-17 13:23:02.212640

Blue-green note: additive only. The previous release neither reads nor writes any of
this, and the new columns are nullable with NULL meaning "reminder off", so the old code
running beside it is unaffected.

`weekly_reminder_sent_on` is both a record and a lock: the conditional UPDATE that
advances it ("set it to today where it isn't already today") is what makes exactly one
replica win the race to send. That's why there's no deliveries table here — a ledger
earns its keep across many notification kinds, and there is one.

Autogenerate also wanted to convert `logs.confidence` and `logs.raw_ai_response` from
JSON to JSONB. That's pre-existing drift between the model and the database, first noted
in d0563dd9088f and deliberately left alone there too: it's unrelated to this change, and
rewriting a column type on a live table is not something to slip into a deploy about
notifications.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "af364567dc8e"
down_revision: str | None = "a1c4e7f09b22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # Re-subscribing a browser returns the same endpoint. Unique so that becomes an
        # update rather than a second row that would deliver its own copy of every
        # notification.
        sa.UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
    )
    op.create_index(
        op.f("ix_push_subscriptions_user_id"), "push_subscriptions", ["user_id"], unique=False
    )

    op.add_column("user_profiles", sa.Column("weekly_reminder_hour", sa.Integer(), nullable=True))
    op.add_column("user_profiles", sa.Column("weekly_reminder_sent_on", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_profiles", "weekly_reminder_sent_on")
    op.drop_column("user_profiles", "weekly_reminder_hour")
    op.drop_index(op.f("ix_push_subscriptions_user_id"), table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
