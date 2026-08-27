"""user_profiles.timezone (per-user IANA timezone)

Revision ID: a1c4e7f09b22
Revises: 132f8d2a5d18
Create Date: 2026-08-27 12:00:00.000000

Blue-green note: additive only. The previous release ignores this column; the new
release treats NULL as "UTC day boundaries", i.e. exactly today's behaviour until a
value is written. No backfill — the SPA seeds it from the browser on next sign-in.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4e7f09b22"
down_revision: str | None = "132f8d2a5d18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("timezone", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("user_profiles", "timezone")
