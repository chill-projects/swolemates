#!/usr/bin/env python
"""Put enough data in the local database to actually look at the app.

    make seed          # seeds DEV_USER_SUB plus a second user
    make seed-reset    # wipe and re-seed

The second user exists so isolation bugs are visible by eye: if anything belonging to
`dev_partner_...` ever shows up in your session, the scoping is wrong.
"""

import asyncio
import sys

from app.config import get_settings
from app.db import dispose_engine, get_sessionmaker
from app.models.profile import WeightUnit
from app.services import nutrition as nutrition_service
from app.services import profile as profile_service

PARTNER_SUB = "dev_partner_11111111"

NUTRITION_GOALS = [
    {"trackable_key": "calories", "target_value": 2200, "is_streak_target": True},
    {"trackable_key": "protein_g", "target_value": 150},
]

NUTRITION_LOGS = [
    {
        "entries": [
            {"trackable_key": "calories", "value": 450},
            {"trackable_key": "protein_g", "value": 32},
            {"trackable_key": "carbs_g", "value": 48},
            {"trackable_key": "fat_g", "value": 12},
            {"trackable_key": "fiber_g", "value": 3},
        ],
        "name": "chicken and rice",
        "meal_type": "lunch",
    },
    {
        "entries": [
            {"trackable_key": "calories", "value": 180},
            {"trackable_key": "protein_g", "value": 25},
            {"trackable_key": "carbs_g", "value": 9},
            {"trackable_key": "fat_g", "value": 3},
        ],
        "name": "protein shake",
        "meal_type": "snack",
    },
]


async def seed(*, reset: bool) -> None:
    settings = get_settings()
    if not settings.is_local:
        raise SystemExit("refusing to seed outside local dev (ENVIRONMENT != local)")

    me = settings.dev_user_sub
    async with get_sessionmaker()() as session:
        # Idempotent regardless of --reset — a profile is one row per user, so
        # re-running this just re-applies the same values, no accumulation risk.
        await profile_service.update_profile(
            session, me, weight_unit=WeightUnit.lbs, coach_notes="Seeded dev profile."
        )
        await profile_service.complete_onboarding(session, me)
        await profile_service.update_profile(session, PARTNER_SUB, weight_unit=WeightUnit.kg)
        await profile_service.complete_onboarding(session, PARTNER_SUB)

        # Idempotent regardless of --reset — goals upsert by (user, trackable_key).
        await nutrition_service.set_goals(session, me, goals=NUTRITION_GOALS)

        today = await nutrition_service.get_nutrition_day(session, me)
        if today.logs and not reset:
            print(
                f"{me} already has {len(today.logs)} log(s) today; nothing to do. "
                "Use `make seed-reset`."
            )
            return

        for log in NUTRITION_LOGS:
            await nutrition_service.log_nutrition(session, me, **log)
        await session.commit()

    print(
        f"Seeded profiles for {me} and {PARTNER_SUB}, "
        f"plus goals + {len(NUTRITION_LOGS)} nutrition logs for {me}."
    )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(seed(reset="--reset" in sys.argv))
