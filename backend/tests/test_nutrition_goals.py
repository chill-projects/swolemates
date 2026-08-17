import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import nutrition as service
from tests.conftest import TEST_USER


async def test_updating_an_existing_goal_alongside_a_streak_target_over_rest(
    client: AsyncClient,
) -> None:
    """Regression: GoalIn.model_dump() sends is_streak_target=None for entries that
    omit it, which previously overwrote an *existing* goal's flag with NULL (a 500)
    instead of leaving it alone — only reproduced through REST, where the omitted key
    still arrives in the payload."""
    await client.put(
        "/api/nutrition/goals",
        json={"goals": [{"trackable_key": "protein_g", "target_value": "150"}]},
    )

    resp = await client.put(
        "/api/nutrition/goals",
        json={
            "goals": [
                {"trackable_key": "calories", "target_value": "2200", "is_streak_target": True},
                {"trackable_key": "protein_g", "target_value": "160"},
            ]
        },
    )

    assert resp.status_code == 200
    by_key = {g["trackable_key"]: g for g in resp.json()}
    assert by_key["protein_g"]["is_streak_target"] is False
    assert by_key["protein_g"]["target_value"] == "160"
    assert by_key["calories"]["is_streak_target"] is True


async def test_set_goals_400s_over_rest_for_a_non_streak_eligible_trackable(
    client: AsyncClient,
) -> None:
    """Regression: set_goals' streak-eligibility ValueError (#19) wasn't caught by
    this route, so it 500'd instead of 400ing — caught live while smoke-testing."""
    resp = await client.put(
        "/api/nutrition/goals",
        json={
            "goals": [
                {"trackable_key": "weight_lbs", "target_value": "125", "is_streak_target": True}
            ]
        },
    )
    assert resp.status_code == 400


async def test_set_then_get_goals_over_rest(client: AsyncClient) -> None:
    resp = await client.put(
        "/api/nutrition/goals",
        json={"goals": [{"trackable_key": "calories", "target_value": "2200"}]},
    )
    assert resp.status_code == 200

    listed = await client.get("/api/nutrition/goals")
    assert listed.json()[0]["trackable_key"] == "calories"
    assert listed.json()[0]["target_value"] == "2200"


async def test_set_goals_then_get_goals_round_trips(session: AsyncSession) -> None:
    await service.set_goals(
        session, TEST_USER, goals=[{"trackable_key": "calories", "target_value": 2200}]
    )
    await session.flush()

    goals = await service.get_goals(session, TEST_USER)

    assert len(goals) == 1
    assert goals[0].trackable_key == "calories"
    assert float(goals[0].target_value) == 2200


async def test_setting_a_new_streak_target_clears_the_old_one(session: AsyncSession) -> None:
    await service.set_goals(
        session,
        TEST_USER,
        goals=[
            {"trackable_key": "calories", "target_value": 2200, "is_streak_target": True},
            {"trackable_key": "protein_g", "target_value": 150},
        ],
    )
    await session.flush()

    await service.set_goals(
        session,
        TEST_USER,
        goals=[{"trackable_key": "protein_g", "target_value": 150, "is_streak_target": True}],
    )
    await session.flush()

    goals = {g.trackable_key: g for g in await service.get_goals(session, TEST_USER)}
    assert goals["calories"].is_streak_target is False
    assert goals["protein_g"].is_streak_target is True


async def test_set_goals_rejects_streak_target_on_a_non_streak_eligible_trackable(
    session: AsyncSession,
) -> None:
    """weight_lbs is goal-eligible but not streak-eligible (#19, resolved) — a flat
    or rising weigh-in during genuine recomposition isn't a "miss" the way a
    calorie overshoot is."""
    with pytest.raises(ValueError, match="weight_lbs"):
        await service.set_goals(
            session,
            TEST_USER,
            goals=[{"trackable_key": "weight_lbs", "target_value": 140, "is_streak_target": True}],
        )
