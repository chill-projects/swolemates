"""drop tmpx_items

Revision ID: 4f2e6a7c9d31
Revises: 9d03de942151
Create Date: 2026-08-18 12:00:00.000000

Blue-green note: this is a deliberate, narrow exception to the usual "never drop or
rename in the same deploy that stops using it" rule. That rule protects the previous
release while it's still serving traffic during rollover — but TmpX (the disposable
template slice, see README.md/docs/design.md §3) already has zero live traffic; the SPA
route was replaced by NutritionPage back in nutrition slice 2, and this same deploy
deletes every line of code that ever queried tmpx_items. No deployed version (old or
new) reaches this table after this point.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4f2e6a7c9d31"
down_revision: str | None = "9d03de942151"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_tmpx_items_user_id_created_at", table_name="tmpx_items")
    op.drop_table("tmpx_items")


def downgrade() -> None:
    op.create_table(
        "tmpx_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tmpx_items")),
    )
    op.create_index(
        "ix_tmpx_items_user_id_created_at", "tmpx_items", ["user_id", "created_at"], unique=False
    )
