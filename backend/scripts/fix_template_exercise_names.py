#!/usr/bin/env python
"""One-off: repoint one user's 4 saved templates' exercises at the correct real
catalog exercise, per the mapping worked out in chat on 2026-08-26 (each one
confirmed interactively — see conversation history, not re-derived here).

"Hip Abductor/Adductor (machine)" bundled two different movements under one
name; it's split into two TemplateExercise rows — one repointed to the real
catalog match (adduction), one a brand-new custom exercise (abduction, which
the catalog has no entry for at all) tagged muscle_group="legs" so it's at
least correctly categorized even without real muscle-map data.

    uv run python scripts/fix_template_exercise_names.py          # dry run
    uv run python scripts/fix_template_exercise_names.py --apply  # writes

DATABASE_URL controls which database this hits, same as the app itself.
"""

import argparse
import asyncio
import uuid

from sqlalchemy import select

from app.db import dispose_engine, get_sessionmaker
from app.models.workouts import TemplateExercise
from app.services.workouts import _resolve_exercise

USER_SUB = "user_01KYR5KXQV2R9SZBVTCG6TCCKT"

# template_exercise_id -> exact catalog name to repoint at.
REPOINTS: dict[str, str] = {
    # Full Body Day
    "eb153fd1-0d40-48b2-8676-62259d4f43aa": "Arnold Press",
    "760bc557-67b9-4b38-ba61-bf4cc6fe9d21": "Lat Pulldown",
    "f32bbe5b-23b9-474e-952f-51a43ea75935": "Seated Cable Row",
    "ccafdf58-ca3b-4f34-a795-55d55c85113f": "Dumbbell Rear Lunge",
    "f0746ffb-937c-4d7c-991a-3aeba384e9e0": "Cable Seated Lateral Raise",
    # Leg Day (Wide-Leg Sumo Squat deliberately left alone — no clean match)
    "319d4112-de53-4140-8973-77f345fab01e": "Leg Press",
    "5da72870-69bc-48bd-85dc-e8d5d3271f57": "Hip Thrust",
    "f3dac8b3-7072-4b29-9649-5057688d94b6": "Seated Leg Curl",
    "9bf93825-c2c5-4dd4-89e5-1bbdd5f09daf": "Romanian Deadlift",
    "5f41356f-6ad2-4396-806e-79295e9618dc": "One-Legged Cable Kickback",
    # Pull Day
    "82487cf0-dc28-484f-9dcf-e3d1a7ce7221": "Dumbbell Row",
    "2975b10c-7550-4481-a00c-72358ddbc35a": "Seated Cable Row",
    "10d13a53-f659-4577-bcd4-b43564517c2f": "Barbell Curl",
    "26e543c8-29d3-46cc-ba0b-2327d15f17aa": "Face Pull",
    "8bd4e28e-f759-4c90-a316-6e07781a27a3": "Cable Rear Delt Fly",
    # Push Day
    "24d95384-606d-4273-ac67-4f3f36b047e9": "Dumbbell Bench Press",
    "13527d41-e1d8-46e0-928f-0441c697388c": "Dumbbell Shoulder Press",
    "3bd1c8c9-b1b6-4e12-bd19-c6c9698e69a8": "Chest Fly (Machine)",
    "63a8ff12-7eb3-4766-9aad-5ee48f17100d": "Lateral Raise",
    "24905927-d2ba-40f5-82d2-a3bfa6138b79": "Cable Rope Overhead Triceps Extension",
    "839eca9d-4308-4a0e-83af-054cd3bea3d8": "Push-Ups - Close Triceps Position",
}

SPLIT_TEMPLATE_EXERCISE_ID = "81f6e45c-bc52-477d-b202-b452515be027"  # Hip Abductor/Adductor
SPLIT_PRIMARY_NAME = "Cable Hip Adduction"  # real catalog match
SPLIT_NEW_NAME = "Cable Hip Abduction"  # new custom exercise — catalog has no abduction entry
SPLIT_NEW_MUSCLE_GROUP = "legs"


async def run(*, apply: bool) -> None:
    async with get_sessionmaker()() as session:
        changes: list[str] = []

        for te_id, new_name in REPOINTS.items():
            te = await session.get(TemplateExercise, uuid.UUID(te_id))
            if te is None:
                changes.append(f"SKIP {te_id}: not found")
                continue
            resolved = await _resolve_exercise(session, USER_SUB, new_name)
            changes.append(f"{te_id} -> {resolved.id} ({new_name})")
            if apply:
                te.exercise_id = resolved.id

        split_te = await session.get(TemplateExercise, uuid.UUID(SPLIT_TEMPLATE_EXERCISE_ID))
        if split_te is None:
            changes.append(f"SKIP split {SPLIT_TEMPLATE_EXERCISE_ID}: not found")
        else:
            primary = await _resolve_exercise(session, USER_SUB, SPLIT_PRIMARY_NAME)
            new_custom = await _resolve_exercise(
                session, USER_SUB, SPLIT_NEW_NAME, muscle_group=SPLIT_NEW_MUSCLE_GROUP
            )
            changes.append(
                f"{SPLIT_TEMPLATE_EXERCISE_ID} -> split into {primary.id} ({SPLIT_PRIMARY_NAME}) "
                f"+ new row for {new_custom.id} ({SPLIT_NEW_NAME}, "
                f"muscle_group={SPLIT_NEW_MUSCLE_GROUP})"
            )
            if apply:
                split_te.exercise_id = primary.id
                result = await session.execute(
                    select(TemplateExercise)
                    .where(TemplateExercise.template_id == split_te.template_id)
                    .order_by(TemplateExercise.order_index)
                )
                for sibling in result.scalars():
                    if sibling.order_index > split_te.order_index:
                        sibling.order_index += 1
                session.add(
                    TemplateExercise(
                        template_id=split_te.template_id,
                        exercise_id=new_custom.id,
                        order_index=split_te.order_index + 1,
                        target_sets=split_te.target_sets,
                        target_reps=split_te.target_reps,
                        target_seconds=split_te.target_seconds,
                        target_weight=split_te.target_weight,
                        notes=split_te.notes,
                    )
                )

        print("\n".join(changes))
        verb = "Applied" if apply else "Would apply"
        print(f"\n{verb}: {len(changes)} changes.")
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
    asyncio.run(run(apply=args.apply))
