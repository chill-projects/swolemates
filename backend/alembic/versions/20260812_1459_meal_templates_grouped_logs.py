"""meal templates + grouped logs

Revision ID: 535ecdadea6e
Revises: 5406f199aaed
Create Date: 2026-08-12 14:59:30.010407

Blue-green note: this runs while the previous release is still serving traffic. Additive
changes only — no drops or renames in the same deploy that stops using the column.

Autogenerate also proposed converting logs.confidence/raw_ai_response from JSON to
JSONB — pre-existing model/DB drift (the model already declared JSONB; the original
migration used plain JSON) unrelated to meal templates. Left out of this migration
deliberately; worth its own dedicated change.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "535ecdadea6e"
down_revision: str | None = "5406f199aaed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meal_templates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("default_meal_type", sa.String(length=20), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meal_templates")),
    )
    op.create_index("ix_meal_templates_user_id", "meal_templates", ["user_id"], unique=False)

    op.create_table(
        "meal_template_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("serving_description", sa.String(length=200), nullable=True),
        sa.Column("item_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["meal_templates.id"],
            name=op.f("fk_meal_template_items_template_id_meal_templates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meal_template_items")),
    )
    op.create_index(
        "ix_meal_template_items_template_id", "meal_template_items", ["template_id"], unique=False
    )

    op.create_table(
        "meal_template_item_values",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("template_item_id", sa.UUID(), nullable=False),
        sa.Column("trackable_key", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.ForeignKeyConstraint(
            ["template_item_id"],
            ["meal_template_items.id"],
            name=op.f("fk_meal_template_item_values_template_item_id_meal_template_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trackable_key"],
            ["trackable_types.key"],
            name=op.f("fk_meal_template_item_values_trackable_key_trackable_types"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meal_template_item_values")),
    )
    op.create_index(
        "ix_meal_template_item_values_template_item_id",
        "meal_template_item_values",
        ["template_item_id"],
        unique=False,
    )

    op.add_column("logs", sa.Column("group_id", sa.UUID(), nullable=True))
    op.add_column("logs", sa.Column("group_name", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("logs", "group_name")
    op.drop_column("logs", "group_id")
    op.drop_index(
        "ix_meal_template_item_values_template_item_id", table_name="meal_template_item_values"
    )
    op.drop_table("meal_template_item_values")
    op.drop_index("ix_meal_template_items_template_id", table_name="meal_template_items")
    op.drop_table("meal_template_items")
    op.drop_index("ix_meal_templates_user_id", table_name="meal_templates")
    op.drop_table("meal_templates")
