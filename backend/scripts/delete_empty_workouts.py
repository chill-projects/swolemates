#!/usr/bin/env python
"""One-off: delete specific workouts by ID — for aborted/test sessions that got
exercises added (or not) but never had any real sets logged. Refuses to delete
anything that actually has logged sets, as a safety check.

FK cascades handle cleanup: deleting a Workout cascades to its WorkoutExercise
rows, which cascade to their WorkoutSet rows (ondelete="CASCADE" both). A
workout linked to a PlannedWorkout has that link SET NULL on delete, not
blocked — its status is left as-is.

    uv run python scripts/delete_empty_workouts.py <id> [<id> ...]           # dry run
    uv run python scripts/delete_empty_workouts.py <id> [<id> ...] --apply   # deletes

DATABASE_URL controls which database this hits, same as the app itself.
"""

import argparse
import asyncio
import uuid

from sqlalchemy import func, select

from app.db import dispose_engine, get_sessionmaker
from app.models.workouts import Workout, WorkoutExercise, WorkoutSet


async def run(workout_ids: list[str], *, apply: bool) -> None:
    async with get_sessionmaker()() as session:
        for wid in workout_ids:
            workout = await session.get(Workout, uuid.UUID(wid))
            if workout is None:
                print(f"SKIP {wid}: not found")
                continue

            set_count = (
                await session.execute(
                    select(func.count(WorkoutSet.id))
                    .join(WorkoutExercise, WorkoutSet.workout_exercise_id == WorkoutExercise.id)
                    .where(WorkoutExercise.workout_id == workout.id)
                )
            ).scalar_one()
            exercise_count = (
                await session.execute(
                    select(func.count(WorkoutExercise.id)).where(
                        WorkoutExercise.workout_id == workout.id
                    )
                )
            ).scalar_one()

            label = workout.title or workout.activity_type or "Workout"
            print(
                f"{wid}  {workout.started_at:%Y-%m-%d}  {label}  "
                f"exercises={exercise_count} sets={set_count}"
            )
            if set_count > 0:
                print(f"  REFUSING to delete {wid}: it has {set_count} real logged set(s).")
                continue

            if apply:
                await session.delete(workout)

        verb = "Deleted" if apply else "Would delete"
        print(f"\n{verb} workouts with zero logged sets (see above); refused any with real sets.")
        if apply:
            await session.commit()
        else:
            await session.rollback()
            print("Dry run only — nothing written. Re-run with --apply to persist.")
    await dispose_engine()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workout_ids", nargs="+", help="Workout UUIDs to delete")
    parser.add_argument(
        "--apply", action="store_true", help="Write changes (default: dry run, prints only)"
    )
    args = parser.parse_args()
    asyncio.run(run(args.workout_ids, apply=args.apply))
