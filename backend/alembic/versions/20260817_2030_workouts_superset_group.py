"""workouts: superset_group on workout_exercises

Revision ID: 8dbfef2475b9
Revises: 4b8f6e2c9a17
Create Date: 2026-08-17 20:30:00.000000

Blue-green note: additive-only, no drop/rename in the same deploy.

#3, resolved (slice 2b — the in-workout ui:// component, per
docs/proposals/workouts-v1.md §2/§5 on proto/workouts-v1): deferred in the slice-1
migration's docstring for exactly this slice, now that the accordion UI actually
groups by it. Nullable, no backfill — existing rows mean "solo exercise."
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8dbfef2475b9"
down_revision: str | None = "4b8f6e2c9a17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workout_exercises", sa.Column("superset_group", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("workout_exercises", "superset_group")
