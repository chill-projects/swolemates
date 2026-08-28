import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import ActivityLevel, BiologicalSex, GoalType
from app.services import nutrition as nutrition_service
from app.services import profile as profile_service
from app.services import tdee as service
from tests.conftest import TEST_USER


def test_calculate_targets_matches_the_legacy_worked_example() -> None:
    """25F, 130lbs, moderate activity, recomp — hand-verified against
    docs/legacy/logic/tdee.ts's own formula (BMR=1288.24, TDEE≈1996.77)."""
    inputs = service.TdeeInputs(
        sex=BiologicalSex.female,
        age=25,
        height_in=62,
        weight_lbs=130,
        activity_level=ActivityLevel.moderate,
        goal_type=GoalType.recomp,
    )

    targets, tdee = service.calculate_targets(inputs)

    assert round(tdee) == 1997
    assert targets.calories == 1697  # round(1996.772 * 0.85)
    assert targets.protein_g == 117  # round(130 * 0.9)
    assert targets.carbs_g == 193
    assert targets.fat_g == 51
    assert targets.fiber_g == 24


def test_calculate_bmr_male_vs_female_offset() -> None:
    shared = {"age": 30, "height_in": 70, "weight_lbs": 180}
    male = service.calculate_bmr(sex=BiologicalSex.male, **shared)
    female = service.calculate_bmr(sex=BiologicalSex.female, **shared)
    assert male - female == 166  # male base+5, female base-161


async def test_calculate_and_apply_targets_writes_goals(session: AsyncSession) -> None:
    await profile_service.update_profile(
        session,
        TEST_USER,
        sex=BiologicalSex.female,
        age=25,
        height_in=62,
        activity_level=ActivityLevel.moderate,
        goal_type=GoalType.recomp,
    )
    await nutrition_service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "weight_lbs", "value": 130}]
    )
    await session.flush()

    targets, tdee = await service.calculate_and_apply_targets(session, TEST_USER)

    assert targets.calories == 1697
    assert round(tdee) == 1997

    goals = {g.trackable_key: g for g in await nutrition_service.get_goals(session, TEST_USER)}
    assert float(goals["calories"].target_value) == 1697
    assert float(goals["protein_g"].target_value) == 117
    assert goals["calories"].is_streak_target is False  # never touched by the calculator


async def test_calculate_and_apply_targets_requires_a_complete_profile(
    session: AsyncSession,
) -> None:
    with pytest.raises(ValueError, match="sex"):
        await service.calculate_and_apply_targets(session, TEST_USER)


async def test_calculate_and_apply_targets_requires_a_logged_weight(
    session: AsyncSession,
) -> None:
    await profile_service.update_profile(
        session,
        TEST_USER,
        sex=BiologicalSex.male,
        age=30,
        height_in=70,
        activity_level=ActivityLevel.active,
        goal_type=GoalType.maintain,
    )
    await session.flush()

    with pytest.raises(ValueError, match="logged weight"):
        await service.calculate_and_apply_targets(session, TEST_USER)


async def test_calculate_targets_over_rest(client: AsyncClient) -> None:
    await client.patch(
        "/api/profile",
        json={
            "sex": "female",
            "age": 25,
            "height_in": "62",
            "activity_level": "moderate",
            "goal_type": "recomp",
        },
    )
    await client.post(
        "/api/nutrition/logs",
        json={"entries": [{"trackable_key": "weight_lbs", "value": 130}]},
    )

    resp = await client.post("/api/tdee/calculate-targets")

    assert resp.status_code == 200
    body = resp.json()
    assert body["calories"] == 1697
    assert body["protein_g"] == 117

    goals = await client.get("/api/nutrition/goals")
    by_key = {g["trackable_key"]: g for g in goals.json()}
    assert float(by_key["calories"]["target_value"]) == 1697


async def test_calculate_targets_over_rest_400s_without_a_profile(client: AsyncClient) -> None:
    resp = await client.post("/api/tdee/calculate-targets")
    assert resp.status_code == 400


async def test_tdee_estimate_matches_the_calculation_without_persisting(
    client: AsyncClient,
) -> None:
    """The read endpoint is the whole point of the split: same numbers, no write. A
    Profile page that showed the estimate by POSTing would silently replace whatever
    targets the user had set by hand."""
    await client.patch(
        "/api/profile",
        json={
            "sex": "female",
            "age": 25,
            "height_in": "62",
            "activity_level": "moderate",
            "goal_type": "recomp",
        },
    )
    await client.post(
        "/api/nutrition/logs",
        json={"entries": [{"trackable_key": "weight_lbs", "value": 130}]},
    )
    await client.put(
        "/api/nutrition/goals",
        json={"goals": [{"trackable_key": "calories", "target_value": 2000}]},
    )

    resp = await client.get("/api/tdee")

    assert resp.status_code == 200
    body = resp.json()
    assert body["calories"] == 1697
    assert body["protein_g"] == 117
    assert body["missing"] == []

    # The hand-set target survived — nothing was written.
    goals = await client.get("/api/nutrition/goals")
    by_key = {g["trackable_key"]: g for g in goals.json()}
    assert float(by_key["calories"]["target_value"]) == 2000


async def test_tdee_estimate_names_what_is_missing_instead_of_erroring(
    client: AsyncClient,
) -> None:
    resp = await client.get("/api/tdee")

    assert resp.status_code == 200
    body = resp.json()
    assert body["tdee"] is None
    assert "sex" in body["missing"]
    assert "a logged weight" in body["missing"]
