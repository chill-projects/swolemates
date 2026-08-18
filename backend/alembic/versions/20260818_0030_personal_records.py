"""personal_records

Revision ID: 9d03de942151
Revises: 991a88372b60
Create Date: 2026-08-18 00:30:00.000000

Blue-green note: additive-only, no drop/rename in the same deploy.

#3, resolved (slice 4 — streaks & PR celebrations, per
docs/proposals/workouts-v1.md §2/§6 on proto/workouts-v1). A mutable current-record
cache (resolved decision #4) — one row per (user_id, exercise_id, kind), upserted in
place, not an append-only log.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "9d03de942151"
down_revision: str | None = "991a88372b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No manual .create() here: op.create_table() below auto-creates the inline
    # enum type; calling both double-creates it (caught live in an earlier slice).
    op.create_table(
        "personal_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("exercise_id", UUID(as_uuid=True), sa.ForeignKey("exercises.id"), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("weight", "e1rm", name="personal_record_kind"),
            nullable=False,
        ),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column(
            "workout_set_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workout_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("achieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "exercise_id",
            "kind",
            name="uq_personal_records_user_id_exercise_id_kind",
        ),
    )


def downgrade() -> None:
    op.drop_table("personal_records")
    personal_record_kind = sa.Enum(name="personal_record_kind")
    personal_record_kind.drop(op.get_bind(), checkfirst=True)
