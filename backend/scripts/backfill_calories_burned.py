#!/usr/bin/env python
"""One-off backfill: fill calories_burned for completed workouts/activities that
never got an estimate, because the caller's bodyweight wasn't on file yet at the
time (`estimate_calories_burned` only ever computes at write-time and never
retroactively recomputes). Uses whichever weight is on file now, same MET
formula and constants as `finish_workout`/`log_activity`.

    uv run python scripts/backfill_calories_burned.py            # dry run — prints, writes nothing
    uv run python scripts/backfill_calories_burned.py --apply    # writes

DATABASE_URL (same env var the app itself reads) controls which database this
hits — point it at production deliberately. Unlike seed.py, there's no
local-only guard here: this script exists specifically to run against real
account data.
"""

import argparse
import asyncio

from sqlalchemy import select

from app.db import dispose_engine, get_sessionmaker
from app.models.workouts import Workout, WorkoutType
from app.services.workouts import (
    _ACTIVITY_MET,
    _DEFAULT_ACTIVITY_MET,
    _STRENGTH_MET,
    estimate_calories_burned,
)


async def backfill(*, apply: bool) -> None:
    async with get_sessionmaker()() as session:
        result = await session.execute(
            select(Workout).where(
                Workout.completed_at.is_not(None),
                Workout.calories_burned.is_(None),
            )
        )
        workouts = list(result.scalars())

        updated = 0
        skipped_no_duration = 0
        skipped_no_weight = 0
        for w in workouts:
            if w.workout_type == WorkoutType.activity:
                duration = w.duration_minutes or 0
                met = _ACTIVITY_MET.get(
                    (w.activity_type or "").strip().lower(), _DEFAULT_ACTIVITY_MET
                )
            else:
                duration = int((w.completed_at - w.started_at).total_seconds() // 60)
                met = _STRENGTH_MET

            if duration <= 0:
                skipped_no_duration += 1
                continue

            calories = await estimate_calories_burned(
                session, w.user_id, met=met, duration_minutes=duration
            )
            if calories is None:
                skipped_no_weight += 1
                continue

            label = w.activity_type or "strength"
            print(f"{w.id}  {w.started_at:%Y-%m-%d}  {label} ({duration}min) -> {calories} kcal")
            if apply:
                w.calories_burned = calories
                w.calories_source = "estimated"
            updated += 1

        verb = "Applied" if apply else "Would apply"
        print(
            f"\n{verb}: {updated}  |  "
            f"skipped (no real duration): {skipped_no_duration}  |  "
            f"skipped (no weight on file for that user): {skipped_no_weight}  |  "
            f"candidates checked: {len(workouts)}"
        )
        if apply:
            await session.commit()
        else:
            await session.rollback()
            print("\nDry run only — nothing written. Re-run with --apply to persist.")
    await dispose_engine()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Write changes (default: dry run, prints only)"
    )
    args = parser.parse_args()
    asyncio.run(backfill(apply=args.apply))
