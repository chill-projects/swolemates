"""user profiles

Revision ID: 6a300344452c
Revises: 042c45622482
Create Date: 2026-08-11 15:00:00.000000

Blue-green note: this runs while the previous release is still serving traffic. Additive
changes only — no drops or renames in the same deploy that stops using the column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6a300344452c"
down_revision: str | None = "042c45622482"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

weight_unit = sa.Enum("lbs", "kg", name="weight_unit")


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("weight_unit", weight_unit, nullable=False, server_default="lbs"),
        sa.Column("coach_notes", sa.Text(), nullable=True),
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_profiles")),
    )


def downgrade() -> None:
    op.drop_table("user_profiles")
    weight_unit.drop(op.get_bind())
