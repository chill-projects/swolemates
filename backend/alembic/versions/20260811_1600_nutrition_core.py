"""nutrition core: trackable_types, logs, log_values, goals

Revision ID: 5406f199aaed
Revises: 6a300344452c
Create Date: 2026-08-11 16:00:00.000000

Blue-green note: this runs while the previous release is still serving traffic. Additive
changes only — no drops or renames in the same deploy that stops using the column.

Seeds the 5 starter trackable_types (calories/protein_g/carbs_g/fat_g/fiber_g) as part
of this migration, since this app has no other pre-deploy seeding step (docs/design.md
§5: only `alembic upgrade head` runs pre-deploy). Adding a 6th trackable later is a new
migration inserting one row — never a schema change (#4, resolved).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5406f199aaed"
down_revision: str | None = "6a300344452c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STARTER_TRACKABLE_TYPES = [
    ("calories", "Calories", "kcal", "nutrition", True),
    ("protein_g", "Protein", "g", "nutrition", True),
    ("carbs_g", "Carbs", "g", "nutrition", True),
    ("fat_g", "Fat", "g", "nutrition", True),
    ("fiber_g", "Fiber", "g", "nutrition", True),
]


def upgrade() -> None:
    op.create_table(
        "trackable_types",
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("goal_eligible", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_trackable_types")),
    )

    trackable_types = sa.table(
        "trackable_types",
        sa.column("key", sa.String),
        sa.column("label", sa.String),
        sa.column("unit", sa.String),
        sa.column("category", sa.String),
        sa.column("goal_eligible", sa.Boolean),
    )
    op.bulk_insert(
        trackable_types,
        [
            {"key": k, "label": lbl, "unit": u, "category": c, "goal_eligible": g}
            for k, lbl, u, c, g in STARTER_TRACKABLE_TYPES
        ],
    )

    op.create_table(
        "logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("photo_storage_path", sa.String(length=500), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("serving_description", sa.String(length=200), nullable=True),
        sa.Column("meal_type", sa.String(length=20), nullable=True),
        sa.Column("confidence", sa.JSON(), nullable=True),
        sa.Column("raw_ai_response", sa.JSON(), nullable=True),
        sa.Column("edited_by_user", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_logs")),
    )
    op.create_index("ix_logs_user_id_logged_at", "logs", ["user_id", "logged_at"], unique=False)

    op.create_table(
        "log_values",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("log_id", sa.UUID(), nullable=False),
        sa.Column("trackable_key", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.ForeignKeyConstraint(
            ["log_id"], ["logs.id"], name=op.f("fk_log_values_log_id_logs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["trackable_key"],
            ["trackable_types.key"],
            name=op.f("fk_log_values_trackable_key_trackable_types"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_log_values")),
    )
    op.create_index("ix_log_values_log_id", "log_values", ["log_id"], unique=False)

    op.create_table(
        "goals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("trackable_key", sa.String(length=50), nullable=False),
        sa.Column("target_value", sa.Numeric(), nullable=False),
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.Column("is_streak_target", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["trackable_key"],
            ["trackable_types.key"],
            name=op.f("fk_goals_trackable_key_trackable_types"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_goals")),
        sa.UniqueConstraint("user_id", "trackable_key", name="uq_goals_user_id_trackable_key"),
    )


def downgrade() -> None:
    op.drop_table("goals")
    op.drop_index("ix_log_values_log_id", table_name="log_values")
    op.drop_table("log_values")
    op.drop_index("ix_logs_user_id_logged_at", table_name="logs")
    op.drop_table("logs")
    op.drop_table("trackable_types")
