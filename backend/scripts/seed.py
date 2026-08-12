#!/usr/bin/env python
"""Put enough data in the local database to actually look at the app.

    make seed          # seeds DEV_USER_SUB plus a second user
    make seed-reset    # wipe and re-seed

The second user exists so isolation bugs are visible by eye: if anything belonging to
`dev_partner_...` ever shows up in your session, the scoping is wrong.
"""

import asyncio
import sys

from sqlalchemy import delete

from app.config import get_settings
from app.db import dispose_engine, get_sessionmaker
from app.models.profile import WeightUnit
from app.models.tmpx import TmpxItem
from app.services import profile as profile_service
from app.services import tmpx as tmpx_service

PARTNER_SUB = "dev_partner_11111111"

TMPX_SEED = [("first template item", 1), ("second template item", 2), ("third template item", 3)]


async def seed(*, reset: bool) -> None:
    settings = get_settings()
    if not settings.is_local:
        raise SystemExit("refusing to seed outside local dev (ENVIRONMENT != local)")

    me = settings.dev_user_sub
    async with get_sessionmaker()() as session:
        if reset:
            await session.execute(delete(TmpxItem).where(TmpxItem.user_id.in_([me, PARTNER_SUB])))

        # Idempotent regardless of --reset — a profile is one row per user, so
        # re-running this just re-applies the same values, no accumulation risk.
        await profile_service.update_profile(
            session, me, weight_unit=WeightUnit.lbs, coach_notes="Seeded dev profile."
        )
        await profile_service.complete_onboarding(session, me)
        await profile_service.update_profile(session, PARTNER_SUB, weight_unit=WeightUnit.kg)
        await profile_service.complete_onboarding(session, PARTNER_SUB)

        existing = await tmpx_service.list_items(session, me)
        if existing and not reset:
            print(
                f"{me} already has {len(existing)} item(s); nothing to do. Use `make seed-reset`."
            )
            return

        for name, value in TMPX_SEED:
            await tmpx_service.add_item(session, me, name=name, value=value)
        await tmpx_service.add_item(
            session, PARTNER_SUB, name="PARTNER ITEM — you should never see this", value=999
        )
        await session.commit()

    print(
        f"Seeded profiles for {me} and {PARTNER_SUB}, "
        f"plus {len(TMPX_SEED)} tmpx items for {me}, plus 1 for {PARTNER_SUB}."
    )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(seed(reset="--reset" in sys.argv))
