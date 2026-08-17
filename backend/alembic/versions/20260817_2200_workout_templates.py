"""workout templates: workout_templates, template_exercises, target_* on
workout_exercises

Revision ID: 7a3232f713f6
Revises: 8dbfef2475b9
Create Date: 2026-08-17 22:00:00.000000

Blue-green note: additive-only, no drop/rename in the same deploy.

#3, resolved (slice 3a — templates, per docs/proposals/workouts-v1.md §2/§3 on
proto/workouts-v1): the prescription is uniform per exercise (sets x reps @ weight),
not per set, so `target_*` lands on `workout_exercises`/`template_exercises` rather
than reusing `workout_sets.prescribed_*` (which predates that decision and stays
unused).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "7a3232f713f6"
down_revision: str | None = "8dbfef2475b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workout_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_workout_templates_user_id", "workout_templates", ["user_id"])

    op.create_table(
        "template_exercises",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workout_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("exercise_id", UUID(as_uuid=True), sa.ForeignKey("exercises.id"), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("superset_group", sa.Integer(), nullable=True),
        sa.Column("target_sets", sa.Integer(), nullable=False),
        sa.Column("target_reps", sa.Integer(), nullable=True),
        sa.Column("target_seconds", sa.Integer(), nullable=True),
        sa.Column("target_weight", sa.Numeric(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_template_exercises_template_id", "template_exercises", ["template_id"])

    op.add_column("workout_exercises", sa.Column("target_sets", sa.Integer(), nullable=True))
    op.add_column("workout_exercises", sa.Column("target_reps", sa.Integer(), nullable=True))
    op.add_column("workout_exercises", sa.Column("target_seconds", sa.Integer(), nullable=True))
    op.add_column("workout_exercises", sa.Column("target_weight", sa.Numeric(), nullable=True))


def downgrade() -> None:
    op.drop_column("workout_exercises", "target_weight")
    op.drop_column("workout_exercises", "target_seconds")
    op.drop_column("workout_exercises", "target_reps")
    op.drop_column("workout_exercises", "target_sets")
    op.drop_index("ix_template_exercises_template_id", table_name="template_exercises")
    op.drop_table("template_exercises")
    op.drop_index("ix_workout_templates_user_id", table_name="workout_templates")
    op.drop_table("workout_templates")
