"""calories burned: MET-formula estimate

Revision ID: 132f8d2a5d18
Revises: 4e7f808b865c
Create Date: 2026-08-18 20:40:35.113875

Blue-green note: this runs while the previous release is still serving traffic. Additive
changes only — no drops or renames in the same deploy that stops using the column.

Companion to the deferred Apple Watch sync (#24) — a MET-formula fallback for calories
burned, computed only where a real duration exists (log_activity, finish_workout).
`calories_source` is a plain string ("estimated" for now), not a DB enum, so a later
device-sourced value doesn't need an enum-alter migration. No backfill of historical
rows — computing calories is service-layer logic, not migration logic.

Autogenerate also picked up the same pre-existing, unrelated `logs.confidence`/
`raw_ai_response` JSON-vs-JSONB drift noted (and left alone) in prior migrations —
left untouched here too, out of scope.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "132f8d2a5d18"
down_revision: str | None = "4e7f808b865c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workouts", sa.Column("calories_burned", sa.Numeric(), nullable=True))
    op.add_column("workouts", sa.Column("calories_source", sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column("workouts", "calories_source")
    op.drop_column("workouts", "calories_burned")
