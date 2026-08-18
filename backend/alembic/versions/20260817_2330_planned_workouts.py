"""weekly_pattern, planned_workouts

Revision ID: 991a88372b60
Revises: 7a3232f713f6
Create Date: 2026-08-17 23:30:00.000000

Blue-green note: additive-only, no drop/rename in the same deploy.

#3, resolved (slice 3b — weekly pattern + planned workouts, per
docs/proposals/workouts-v1.md §2/§4 on proto/workouts-v1). `weekly_pattern` wasn't
named as a tool anywhere in the doc's own §8 list, but its data model was always
part of the resolved design ("Open question 3" resolution) — built for real here,
per a live decision with Michelle, rather than left as dead schema with no way to
populate it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "991a88372b60"
down_revision: str | None = "7a3232f713f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

planned_workout_status = sa.Enum("planned", "done", "skipped", name="planned_workout_status")


def upgrade() -> None:
    # No manual .create() here: op.create_table() below auto-creates the inline
    # enum type; calling both double-creates it (caught live).
    op.create_table(
        "weekly_pattern",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column(
            "template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workout_templates.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.UniqueConstraint("user_id", "day_of_week", name="uq_weekly_pattern_user_id_day_of_week"),
        sa.CheckConstraint(
            "day_of_week >= 0 AND day_of_week <= 6", name="ck_weekly_pattern_day_of_week"
        ),
    )

    op.create_table(
        "planned_workouts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column(
            "template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workout_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scheduled_for", sa.Date(), nullable=False),
        sa.Column("status", planned_workout_status, nullable=False),
        sa.Column(
            "workout_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workouts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_planned_workouts_user_id_scheduled_for",
        "planned_workouts",
        ["user_id", "scheduled_for"],
    )


def downgrade() -> None:
    op.drop_index("ix_planned_workouts_user_id_scheduled_for", table_name="planned_workouts")
    op.drop_table("planned_workouts")
    op.drop_table("weekly_pattern")
    planned_workout_status.drop(op.get_bind(), checkfirst=True)
