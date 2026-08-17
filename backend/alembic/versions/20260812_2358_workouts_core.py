"""workouts core: exercises, workouts, workout_exercises, workout_sets

Revision ID: 4b8f6e2c9a17
Revises: 7c1e9a4f2b6d
Create Date: 2026-08-12 23:58:00.000000

Blue-green note: this runs while the previous release is still serving traffic. Additive
changes only — no drops or renames in the same deploy that stops using the column.

#3, resolved (slice 1 of 5 — core domain model + one-shot logging, per
docs/proposals/workouts-v1.md §2 on proto/workouts-v1): `template_id` on `workouts`
and `superset_group` on `workout_exercises` are deliberately deferred to later slices
(templates/plans, in-workout mode) rather than added now unused — additive migrations
land exactly when those slices need them, same pattern as nutrition's
`logs.group_id`/`group_name`.

Seeds the 40 legacy starter exercises (docs/legacy/schema/0003_workouts.sql) inside
this migration, following `trackable_types`' precedent: this app has no other
pre-deploy seeding step, and the catalog is shared reference data, not per-user dev
data. `description`/`image_paths`/`source_id` stay NULL for now — the full
873-exercise free-exercise-db vendoring (which populates them) is a separate,
not-yet-scheduled follow-up.
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "4b8f6e2c9a17"
down_revision: str | None = "7c1e9a4f2b6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

workout_type = sa.Enum("strength", "activity", name="workout_type")
set_type = sa.Enum("reps", "time", name="set_type")

# Ported verbatim from docs/legacy/schema/0003_workouts.sql.
STARTER_EXERCISES = [
    ("Barbell Back Squat", "legs", "barbell"),
    ("Front Squat", "legs", "barbell"),
    ("Romanian Deadlift", "legs", "barbell"),
    ("Deadlift", "back", "barbell"),
    ("Hip Thrust", "legs", "barbell"),
    ("Bulgarian Split Squat", "legs", "dumbbell"),
    ("Walking Lunge", "legs", "dumbbell"),
    ("Leg Press", "legs", "machine"),
    ("Leg Curl", "legs", "machine"),
    ("Leg Extension", "legs", "machine"),
    ("Calf Raise", "legs", "machine"),
    ("Barbell Bench Press", "chest", "barbell"),
    ("Incline Barbell Press", "chest", "barbell"),
    ("Dumbbell Bench Press", "chest", "dumbbell"),
    ("Incline Dumbbell Press", "chest", "dumbbell"),
    ("Push-up", "chest", "bodyweight"),
    ("Cable Fly", "chest", "cable"),
    ("Chest Fly (Machine)", "chest", "machine"),
    ("Barbell Row", "back", "barbell"),
    ("Dumbbell Row", "back", "dumbbell"),
    ("Pull-up", "back", "bodyweight"),
    ("Chin-up", "back", "bodyweight"),
    ("Lat Pulldown", "back", "machine"),
    ("Seated Cable Row", "back", "machine"),
    ("Overhead Press", "shoulders", "barbell"),
    ("Dumbbell Shoulder Press", "shoulders", "dumbbell"),
    ("Arnold Press", "shoulders", "dumbbell"),
    ("Lateral Raise", "shoulders", "dumbbell"),
    ("Front Raise", "shoulders", "dumbbell"),
    ("Face Pull", "shoulders", "cable"),
    ("Barbell Curl", "arms", "barbell"),
    ("Dumbbell Curl", "arms", "dumbbell"),
    ("Hammer Curl", "arms", "dumbbell"),
    ("Close-Grip Bench Press", "arms", "barbell"),
    ("Skull Crusher", "arms", "barbell"),
    ("Tricep Pushdown", "arms", "machine"),
    ("Dip", "arms", "bodyweight"),
    ("Plank", "core", "bodyweight"),
    ("Hanging Leg Raise", "core", "bodyweight"),
    ("Cable Crunch", "core", "cable"),
    ("Russian Twist", "core", "bodyweight"),
]


def upgrade() -> None:
    # No manual .create() here: op.create_table() below auto-creates each inline
    # sa.Enum column's Postgres type as part of compiling CREATE TABLE (unlike
    # op.add_column(), which needs an explicit .create() first — see the TDEE
    # migration). Calling both double-creates the type and errors.
    op.create_table(
        "exercises",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("muscle_group", sa.String(length=50), nullable=False),
        sa.Column("equipment", sa.String(length=50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_paths", JSONB(), nullable=True),
        sa.Column("source_id", sa.String(length=100), nullable=True),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exercises")),
        sa.UniqueConstraint("source_id", name=op.f("uq_exercises_source_id")),
    )

    op.create_table(
        "workouts",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("workout_type", workout_type, nullable=False, server_default="strength"),
        sa.Column("activity_type", sa.String(length=100), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workouts")),
        sa.CheckConstraint(
            "(workout_type = 'strength' AND activity_type IS NULL AND duration_minutes IS NULL)"
            " OR (workout_type = 'activity' AND activity_type IS NOT NULL"
            "     AND duration_minutes IS NOT NULL)",
            name=op.f("ck_workouts_workout_type_fields_check"),
        ),
    )
    op.create_index("ix_workouts_user_id_started_at", "workouts", ["user_id", "started_at"])

    op.create_table(
        "workout_exercises",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("workout_id", UUID(as_uuid=True), nullable=False),
        sa.Column("exercise_id", UUID(as_uuid=True), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("next_time_note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["workout_id"],
            ["workouts.id"],
            name=op.f("fk_workout_exercises_workout_id_workouts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.id"],
            name=op.f("fk_workout_exercises_exercise_id_exercises"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workout_exercises")),
    )
    op.create_index("ix_workout_exercises_workout_id", "workout_exercises", ["workout_id"])

    op.create_table(
        "workout_sets",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("workout_exercise_id", UUID(as_uuid=True), nullable=False),
        sa.Column("set_number", sa.Integer(), nullable=False),
        sa.Column("set_type", set_type, nullable=False, server_default="reps"),
        sa.Column("is_warmup", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("prescribed_weight", sa.Numeric(), nullable=True),
        sa.Column("prescribed_reps", sa.Integer(), nullable=True),
        sa.Column("actual_weight", sa.Numeric(), nullable=True),
        sa.Column("actual_reps", sa.Integer(), nullable=True),
        sa.Column("work_seconds", sa.Integer(), nullable=True),
        sa.Column("rest_seconds", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workout_exercise_id"],
            ["workout_exercises.id"],
            name=op.f("fk_workout_sets_workout_exercise_id_workout_exercises"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workout_sets")),
        sa.CheckConstraint(
            "completed_at IS NULL"
            " OR (set_type = 'reps' AND actual_reps IS NOT NULL)"
            " OR (set_type = 'time' AND work_seconds IS NOT NULL)",
            name=op.f("ck_workout_sets_set_type_fields_check"),
        ),
    )
    op.create_index("ix_workout_sets_workout_exercise_id", "workout_sets", ["workout_exercise_id"])

    exercises = sa.table(
        "exercises",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("muscle_group", sa.String),
        sa.column("equipment", sa.String),
    )
    op.bulk_insert(
        exercises,
        [
            {"id": uuid.uuid4(), "name": name, "muscle_group": muscle_group, "equipment": equipment}
            for name, muscle_group, equipment in STARTER_EXERCISES
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_workout_sets_workout_exercise_id", table_name="workout_sets")
    op.drop_table("workout_sets")
    op.drop_index("ix_workout_exercises_workout_id", table_name="workout_exercises")
    op.drop_table("workout_exercises")
    op.drop_index("ix_workouts_user_id_started_at", table_name="workouts")
    op.drop_table("workouts")
    op.drop_table("exercises")

    bind = op.get_bind()
    set_type.drop(bind, checkfirst=True)
    workout_type.drop(bind, checkfirst=True)
