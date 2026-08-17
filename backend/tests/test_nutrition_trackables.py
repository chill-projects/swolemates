from sqlalchemy.ext.asyncio import AsyncSession

from app.services import nutrition as service


async def test_starter_trackable_types_are_seeded(session: AsyncSession) -> None:
    types = await service.list_trackable_types(session)
    by_key = {t.key: t for t in types}

    assert set(by_key) == {
        "calories",
        "protein_g",
        "carbs_g",
        "fat_g",
        "fiber_g",
        "weight_lbs",
    }
    assert all(t.goal_eligible for t in types)
    assert by_key["calories"].unit == "kcal"
    assert by_key["protein_g"].unit == "g"
    # weight_lbs (#19, resolved) is goal-eligible but not streak-eligible; every
    # nutrition macro stays streak-eligible.
    assert by_key["weight_lbs"].streak_eligible is False
    assert all(t.streak_eligible for k, t in by_key.items() if k != "weight_lbs")
