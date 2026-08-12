"""tdee profile fields + weight trackable

Revision ID: 7c1e9a4f2b6d
Revises: 535ecdadea6e
Create Date: 2026-08-12 23:28:00.000000

Blue-green note: this runs while the previous release is still serving traffic. Additive
changes only — no drops or renames in the same deploy that stops using the column.

#19, resolved: TDEE calculator inputs (sex/age/height/activity_level/goal_type) live on
the profile, not nutrition — all nullable, since the calculator is opt-in/re-runnable,
never a hard onboarding gate. Weight itself is a trackable (`weight_lbs`, logged via the
existing logs/log_values model), goal-eligible but not streak-eligible — hence the new
`trackable_types.streak_eligible` column, seeded true for the 5 existing rows and false
for this new one (weight reflects fat *and* muscle, not a daily pass/fail metric the way
calories/protein are).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c1e9a4f2b6d"
down_revision: str | None = "535ecdadea6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

biological_sex = sa.Enum("male", "female", name="biological_sex")
activity_level = sa.Enum(
    "sedentary", "light", "moderate", "active", "very_active", name="activity_level"
)
nutrition_goal_type = sa.Enum(
    "lose_weight", "maintain", "gain_muscle", "recomp", name="nutrition_goal_type"
)

WEIGHT_TRACKABLE = ("weight_lbs", "Weight", "lbs", "body", True, False)


def upgrade() -> None:
    bind = op.get_bind()
    biological_sex.create(bind, checkfirst=True)
    activity_level.create(bind, checkfirst=True)
    nutrition_goal_type.create(bind, checkfirst=True)

    op.add_column("user_profiles", sa.Column("sex", biological_sex, nullable=True))
    op.add_column("user_profiles", sa.Column("age", sa.Integer(), nullable=True))
    op.add_column("user_profiles", sa.Column("height_in", sa.Numeric(), nullable=True))
    op.add_column("user_profiles", sa.Column("activity_level", activity_level, nullable=True))
    op.add_column("user_profiles", sa.Column("goal_type", nutrition_goal_type, nullable=True))

    op.add_column(
        "trackable_types",
        sa.Column("streak_eligible", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    trackable_types = sa.table(
        "trackable_types",
        sa.column("key", sa.String),
        sa.column("label", sa.String),
        sa.column("unit", sa.String),
        sa.column("category", sa.String),
        sa.column("goal_eligible", sa.Boolean),
        sa.column("streak_eligible", sa.Boolean),
    )
    op.bulk_insert(
        trackable_types,
        [
            {
                "key": WEIGHT_TRACKABLE[0],
                "label": WEIGHT_TRACKABLE[1],
                "unit": WEIGHT_TRACKABLE[2],
                "category": WEIGHT_TRACKABLE[3],
                "goal_eligible": WEIGHT_TRACKABLE[4],
                "streak_eligible": WEIGHT_TRACKABLE[5],
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text("delete from trackable_types where key = :key").bindparams(key=WEIGHT_TRACKABLE[0])
    )
    op.drop_column("trackable_types", "streak_eligible")

    op.drop_column("user_profiles", "goal_type")
    op.drop_column("user_profiles", "activity_level")
    op.drop_column("user_profiles", "height_in")
    op.drop_column("user_profiles", "age")
    op.drop_column("user_profiles", "sex")

    bind = op.get_bind()
    nutrition_goal_type.drop(bind, checkfirst=True)
    activity_level.drop(bind, checkfirst=True)
    biological_sex.drop(bind, checkfirst=True)
