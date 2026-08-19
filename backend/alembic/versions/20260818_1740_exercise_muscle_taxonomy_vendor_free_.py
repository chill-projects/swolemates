"""exercise muscle taxonomy: vendor free-exercise-db metadata

Revision ID: b2533d76e782
Revises: d0563dd9088f
Create Date: 2026-08-18 17:40:36.166022

Blue-green note: this runs while the previous release is still serving traffic. Additive
changes only — no drops or renames in the same deploy that stops using the column.

Live-workout muscle map, resolved: `primary_muscles`/`secondary_muscles` (free-exercise-
db's 17-muscle taxonomy) are additive alongside the existing `muscle_group` (the coarse
6-bucket legacy taxonomy, which stays — `_resolve_exercise`'s auto-create-custom-exercise
path only ever sets that one). Vendored metadata-only (no photos/descriptions/instructions
— ticket #15's full vendor, deferred for later): `app/data/exercise_muscles.json`, 873
records of `{id, name, primary_muscles, secondary_muscles}`, live-fetched from
free-exercise-db's `dist/exercises.json` (Unlicense, public domain — no attribution
required). Seeds inside the migration, same precedent as the original 41-starter seed in
`20260812_2358_workouts_core.py`: backfill the 41 existing starters via a verified
name→id mapping (all 41 resolve), then insert the remaining ~832 as new `is_custom=False`
catalog rows with a coarse `muscle_group` derived from each exercise's primary muscle,
since that column stays `NOT NULL`.

Autogenerate also picked up the same pre-existing, unrelated `logs.confidence`/
`raw_ai_response` JSON-vs-JSONB drift noted (and left alone) in the previous migration's
docstring — left untouched here too, out of scope.
"""

import json
import uuid
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2533d76e782"
down_revision: str | None = "d0563dd9088f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "app" / "data" / "exercise_muscles.json"

# Verified (2026-08-18) against a live fetch of free-exercise-db's dist/exercises.json:
# all 41 starters resolve to a real id. Where no exact name match exists, picked the
# closest equipment/movement match by hand (e.g. "Barbell Back Squat" -> "Barbell_Squat",
# "Bulgarian Split Squat" -> "Split_Squat_with_Dumbbells" for the dumbbell RFE variant).
STARTER_TO_SOURCE_ID = {
    "Barbell Back Squat": "Barbell_Squat",
    "Front Squat": "Front_Barbell_Squat",
    "Romanian Deadlift": "Romanian_Deadlift",
    "Deadlift": "Barbell_Deadlift",
    "Hip Thrust": "Barbell_Hip_Thrust",
    "Bulgarian Split Squat": "Split_Squat_with_Dumbbells",
    "Walking Lunge": "Dumbbell_Lunges",
    "Leg Press": "Leg_Press",
    "Leg Curl": "Lying_Leg_Curls",
    "Leg Extension": "Leg_Extensions",
    "Calf Raise": "Seated_Calf_Raise",
    "Barbell Bench Press": "Barbell_Bench_Press_-_Medium_Grip",
    "Incline Barbell Press": "Barbell_Incline_Bench_Press_-_Medium_Grip",
    "Dumbbell Bench Press": "Dumbbell_Bench_Press",
    "Incline Dumbbell Press": "Incline_Dumbbell_Press",
    "Push-up": "Pushups",
    "Cable Fly": "Flat_Bench_Cable_Flyes",
    "Chest Fly (Machine)": "Butterfly",
    "Barbell Row": "Bent_Over_Barbell_Row",
    "Dumbbell Row": "One-Arm_Dumbbell_Row",
    "Pull-up": "Pullups",
    "Chin-up": "Chin-Up",
    "Lat Pulldown": "Wide-Grip_Lat_Pulldown",
    "Seated Cable Row": "Seated_Cable_Rows",
    "Overhead Press": "Standing_Military_Press",
    "Dumbbell Shoulder Press": "Dumbbell_Shoulder_Press",
    "Arnold Press": "Arnold_Dumbbell_Press",
    "Lateral Raise": "Side_Lateral_Raise",
    "Front Raise": "Front_Dumbbell_Raise",
    "Face Pull": "Face_Pull",
    "Barbell Curl": "Barbell_Curl",
    "Dumbbell Curl": "Dumbbell_Bicep_Curl",
    "Hammer Curl": "Hammer_Curls",
    "Close-Grip Bench Press": "Close-Grip_Barbell_Bench_Press",
    "Skull Crusher": "EZ-Bar_Skullcrusher",
    "Tricep Pushdown": "Triceps_Pushdown",
    "Dip": "Dips_-_Triceps_Version",
    "Plank": "Plank",
    "Hanging Leg Raise": "Hanging_Leg_Raise",
    "Cable Crunch": "Cable_Crunch",
    "Russian Twist": "Russian_Twist",
}

# free-exercise-db's 17 primary-muscle values -> this app's pre-existing coarse
# 6-bucket muscle_group taxonomy (legs/back/chest/shoulders/arms/core), so every
# vendored row still satisfies muscle_group's NOT NULL constraint. "neck" has no good
# home in the 6 buckets; falls back to "other" rather than a misleading one.
PRIMARY_TO_MUSCLE_GROUP = {
    "quadriceps": "legs",
    "hamstrings": "legs",
    "calves": "legs",
    "glutes": "legs",
    "adductors": "legs",
    "abductors": "legs",
    "chest": "chest",
    "lats": "back",
    "middle back": "back",
    "lower back": "back",
    "traps": "back",
    "shoulders": "shoulders",
    "biceps": "arms",
    "triceps": "arms",
    "forearms": "arms",
    "abdominals": "core",
    "neck": "other",
}


def upgrade() -> None:
    op.add_column("exercises", sa.Column("primary_muscles", postgresql.JSONB(), nullable=True))
    op.add_column("exercises", sa.Column("secondary_muscles", postgresql.JSONB(), nullable=True))

    exercises = sa.table(
        "exercises",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("muscle_group", sa.String),
        sa.column("equipment", sa.String),
        sa.column("source_id", sa.String),
        sa.column("primary_muscles", postgresql.JSONB),
        sa.column("secondary_muscles", postgresql.JSONB),
        sa.column("is_custom", sa.Boolean),
    )

    vendored = json.loads(DATA_PATH.read_text())
    by_id = {row["id"]: row for row in vendored}

    connection = op.get_bind()
    for starter_name, source_id in STARTER_TO_SOURCE_ID.items():
        row = by_id[source_id]
        connection.execute(
            exercises.update()
            .where(exercises.c.name == starter_name, exercises.c.is_custom.is_(False))
            .values(
                source_id=source_id,
                primary_muscles=row["primary_muscles"],
                secondary_muscles=row["secondary_muscles"],
            )
        )

    used_ids = set(STARTER_TO_SOURCE_ID.values())
    new_rows = [
        {
            "id": uuid.uuid4(),
            "name": row["name"],
            "muscle_group": PRIMARY_TO_MUSCLE_GROUP.get(
                row["primary_muscles"][0] if row["primary_muscles"] else "", "other"
            ),
            "equipment": None,
            "source_id": row["id"],
            "primary_muscles": row["primary_muscles"],
            "secondary_muscles": row["secondary_muscles"],
            "is_custom": False,
        }
        for row in vendored
        if row["id"] not in used_ids
    ]
    if new_rows:
        op.bulk_insert(exercises, new_rows)


def downgrade() -> None:
    op.drop_column("exercises", "secondary_muscles")
    op.drop_column("exercises", "primary_muscles")
