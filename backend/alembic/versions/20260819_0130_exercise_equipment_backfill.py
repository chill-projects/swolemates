"""exercise equipment backfill

Revision ID: 4e7f808b865c
Revises: b2533d76e782
Create Date: 2026-08-19 01:30:00.000000

Blue-green note: this runs while the previous release is still serving traffic. Data-
only — no column changes, `equipment` already exists and stays nullable.

Exercise-picker filtering (category + equipment), resolved: only the 41 legacy
starters had `equipment` set; the 837-row free-exercise-db vendor
(`b2533d76e782`) never backfilled it — the slim `exercise_muscles.json` it read
only carried names + muscles. Fixes that here with a second slim data file,
`app/data/exercise_equipment.json` (873 `{id, equipment}` records, same live
fetch of free-exercise-db's `dist/exercises.json` as the muscle migration).

By the time this runs, `b2533d76e782` has already stamped `source_id` on every
vendored/starter row (873 of the app's 878 exercises — the other 5 are pre-
existing custom exercises with no vendor match), so this is one UPDATE-by-
`source_id` pass covering *both* the 41 starters and the 837 new rows uniformly —
no need to re-derive the starter name mapping. This also naturally normalizes the
41 starters' old `"bodyweight"` tag to free-exercise-db's own `"body only"` (and,
less expected but equally correct, a few other starter/vendor equipment
mismatches inherited from the legacy hand-tagging, e.g. "Seated Cable Row" moving
from the legacy "machine" to free-exercise-db's "cable" — one consistent
vocabulary across all 878 rows beats two independently-tagged ones.
"""

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "4e7f808b865c"
down_revision: str | None = "b2533d76e782"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_PATH = (
    Path(__file__).resolve().parent.parent.parent / "app" / "data" / "exercise_equipment.json"
)


def upgrade() -> None:
    exercises = sa.table(
        "exercises",
        sa.column("source_id", sa.String),
        sa.column("equipment", sa.String),
    )

    equipment_by_id = {row["id"]: row["equipment"] for row in json.loads(DATA_PATH.read_text())}

    connection = op.get_bind()
    for source_id, equipment in equipment_by_id.items():
        if equipment is None:
            continue
        connection.execute(
            exercises.update().where(exercises.c.source_id == source_id).values(equipment=equipment)
        )


def downgrade() -> None:
    # Data-only; no reliable way to restore the pre-vendor equipment values (or
    # lack thereof) for the 837 rows this touches, so downgrade is a no-op —
    # matches b2533d76e782's precedent (columns/rows it added aren't reversed
    # either).
    pass
