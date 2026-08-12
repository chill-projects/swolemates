from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import nutrition as service
from tests.conftest import OTHER_USER, TEST_USER


async def test_post_log_nutrition_writes_entries(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/nutrition/logs",
        json={
            "entries": [
                {"trackable_key": "calories", "value": "450"},
                {"trackable_key": "protein_g", "value": "32"},
            ],
            "name": "chicken and rice",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "chicken and rice"


async def test_set_then_get_goals_over_rest(client: AsyncClient) -> None:
    resp = await client.put(
        "/api/nutrition/goals",
        json={"goals": [{"trackable_key": "calories", "target_value": "2200"}]},
    )
    assert resp.status_code == 200

    listed = await client.get("/api/nutrition/goals")
    assert listed.json()[0]["trackable_key"] == "calories"
    assert listed.json()[0]["target_value"] == "2200"


async def test_five_starter_trackable_types_are_seeded(session: AsyncSession) -> None:
    types = await service.list_trackable_types(session)
    by_key = {t.key: t for t in types}

    assert set(by_key) == {"calories", "protein_g", "carbs_g", "fat_g", "fiber_g"}
    assert all(t.goal_eligible for t in types)
    assert by_key["calories"].unit == "kcal"
    assert by_key["protein_g"].unit == "g"


async def test_log_nutrition_writes_one_header_and_all_values(session: AsyncSession) -> None:
    log = await service.log_nutrition(
        session,
        TEST_USER,
        entries=[
            {"trackable_key": "calories", "value": 450},
            {"trackable_key": "protein_g", "value": 32},
        ],
        name="chicken and rice",
    )
    await session.flush()

    values = await service.get_log_values(session, TEST_USER, log.id)
    by_key = {v.trackable_key: v.value for v in values}

    assert log.name == "chicken and rice"
    assert float(by_key["calories"]) == 450
    assert float(by_key["protein_g"]) == 32


async def test_users_cannot_read_each_others_log_values(session: AsyncSession) -> None:
    """The whole permission model, asserted directly against the service layer."""
    bobs_log = await service.log_nutrition(
        session, OTHER_USER, entries=[{"trackable_key": "calories", "value": 999}]
    )
    await session.flush()

    assert await service.get_log_values(session, TEST_USER, bobs_log.id) == []


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
