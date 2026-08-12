from datetime import UTC, datetime
from uuid import uuid4

import pytest
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


async def test_get_nutrition_day_over_rest(client: AsyncClient) -> None:
    await client.put(
        "/api/nutrition/goals",
        json={"goals": [{"trackable_key": "calories", "target_value": "2200"}]},
    )
    await client.post(
        "/api/nutrition/logs",
        json={
            "entries": [{"trackable_key": "calories", "value": "450"}],
            "name": "chicken and rice",
        },
    )

    resp = await client.get("/api/nutrition/day")

    assert resp.status_code == 200
    body = resp.json()
    assert body["hero"]["trackable_key"] == "calories"
    assert body["hero"]["consumed"] == "450"
    assert body["hero"]["target"] == "2200"
    assert body["logs"][0]["name"] == "chicken and rice"


async def test_meal_template_save_log_delete_round_trips_over_rest(client: AsyncClient) -> None:
    logged = await client.post(
        "/api/nutrition/logs",
        json={"entries": [{"trackable_key": "calories", "value": "180"}], "name": "Eggs"},
    )
    log_id = logged.json()["id"]

    saved = await client.post(
        "/api/nutrition/templates",
        json={"name": "Usual breakfast", "log_ids": [log_id]},
    )
    assert saved.status_code == 201
    template_id = saved.json()["id"]
    assert saved.json()["totals"]["calories"] == "180"

    listed = await client.get("/api/nutrition/templates")
    assert [t["id"] for t in listed.json()] == [template_id]

    logged_from_template = await client.post(
        f"/api/nutrition/templates/{template_id}/log", json={"multiplier": "2"}
    )
    assert logged_from_template.status_code == 201
    assert len(logged_from_template.json()) == 1

    day = await client.get("/api/nutrition/day")
    grouped = [entry for entry in day.json()["logs"] if entry["items"]]
    assert len(grouped) == 1
    assert grouped[0]["values"]["calories"] == "360"  # 180 * 2

    deleted = await client.delete(f"/api/nutrition/templates/{template_id}")
    assert deleted.status_code == 204
    assert (await client.get("/api/nutrition/templates")).json() == []


async def test_log_meal_template_404s_for_unknown_template(client: AsyncClient) -> None:
    resp = await client.post(f"/api/nutrition/templates/{uuid4()}/log", json={})
    assert resp.status_code == 404


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


async def test_update_nutrition_log_patches_only_given_fields(session: AsyncSession) -> None:
    log = await service.log_nutrition(
        session,
        TEST_USER,
        entries=[
            {"trackable_key": "calories", "value": 250},
            {"trackable_key": "protein_g", "value": 5},
        ],
        name="large coffee",
    )
    await session.flush()

    updated = await service.update_nutrition_log(
        session, TEST_USER, log_id=log.id, name="small coffee", values={"calories": 80}
    )

    assert updated.name == "small coffee"
    assert updated.edited_by_user is True
    log_values = await service.get_log_values(session, TEST_USER, log.id)
    values = {v.trackable_key: v.value for v in log_values}
    assert float(values["calories"]) == 80
    assert float(values["protein_g"]) == 5  # untouched — only calories was patched


async def test_update_nutrition_log_404s_for_another_users_log(session: AsyncSession) -> None:
    bobs_log = await service.log_nutrition(
        session, OTHER_USER, entries=[{"trackable_key": "calories", "value": 100}]
    )
    await session.flush()

    with pytest.raises(service.NotFoundError):
        await service.update_nutrition_log(session, TEST_USER, log_id=bobs_log.id, name="hijacked")


async def test_amend_last_log_with_no_fields_deletes_the_most_recent_entry(
    session: AsyncSession,
) -> None:
    # created_at defaults to Postgres now(), which is frozen for an entire
    # transaction — both calls would tie without explicitly staggering it here to
    # simulate the separate transactions two real, sequential tool calls get.
    first = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 100}], name="first"
    )
    await session.flush()
    first.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    last = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 200}], name="second"
    )
    await session.flush()
    last.created_at = datetime(2026, 1, 2, tzinfo=UTC)
    await session.flush()

    updated, log_id, name = await service.amend_last_log(session, TEST_USER)

    assert updated is None
    assert log_id == last.id
    assert name == "second"
    assert await service.get_log_values(session, TEST_USER, last.id) == []


async def test_amend_last_log_with_fields_patches_the_most_recent_entry_in_place(
    session: AsyncSession,
) -> None:
    first = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 100}], name="first"
    )
    await session.flush()
    first.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    last = await service.log_nutrition(
        session,
        TEST_USER,
        entries=[{"trackable_key": "calories", "value": 300}],
        name="large coffee",
    )
    await session.flush()
    last.created_at = datetime(2026, 1, 2, tzinfo=UTC)
    await session.flush()

    updated, log_id, name = await service.amend_last_log(
        session, TEST_USER, name="small coffee", values={"calories": 80}
    )

    assert updated is not None
    assert log_id == last.id
    assert name == "small coffee"
    log_values = await service.get_log_values(session, TEST_USER, last.id)
    values = {v.trackable_key: v.value for v in log_values}
    assert float(values["calories"]) == 80


async def test_amend_last_log_404s_when_nothing_to_amend(session: AsyncSession) -> None:
    with pytest.raises(service.NotFoundError):
        await service.amend_last_log(session, TEST_USER)


async def test_update_and_amend_nutrition_log_over_rest(client: AsyncClient) -> None:
    created = await client.post(
        "/api/nutrition/logs",
        json={"entries": [{"trackable_key": "calories", "value": 250}], "name": "large coffee"},
    )
    log_id = created.json()["id"]

    patched = await client.patch(
        f"/api/nutrition/logs/{log_id}",
        json={"name": "small coffee", "values": {"calories": "80"}},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["name"] == "small coffee"
    assert body["values"]["calories"] == "80"

    amended = await client.post("/api/nutrition/logs/amend-last", json={})
    assert amended.status_code == 200
    assert amended.json() == {"deleted": True, "log": None}


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


async def test_nutrition_day_sums_todays_logs_against_goals(session: AsyncSession) -> None:
    await service.set_goals(
        session,
        TEST_USER,
        goals=[
            {"trackable_key": "calories", "target_value": 2200, "is_streak_target": True},
            {"trackable_key": "protein_g", "target_value": 160},
        ],
    )
    await service.log_nutrition(
        session,
        TEST_USER,
        entries=[
            {"trackable_key": "calories", "value": 450},
            {"trackable_key": "protein_g", "value": 32},
        ],
        name="chicken and rice",
    )
    await service.log_nutrition(
        session,
        TEST_USER,
        entries=[
            {"trackable_key": "calories", "value": 980},
            {"trackable_key": "protein_g", "value": 64},
        ],
        name="burger",
    )
    await session.flush()

    day = await service.get_nutrition_day(session, TEST_USER)

    assert day.hero.trackable_key == "calories"
    assert float(day.hero.consumed) == 1430
    assert float(day.hero.target) == 2200
    assert day.streak_key == "calories"

    bars = {b.trackable_key: b for b in day.bars}
    assert set(bars) == {"protein_g", "carbs_g", "fat_g", "fiber_g"}
    assert float(bars["protein_g"].consumed) == 96
    assert float(bars["protein_g"].target) == 160
    assert float(bars["carbs_g"].consumed) == 0
    assert bars["carbs_g"].target is None

    assert len(day.logs) == 2
    burger = next(log for log in day.logs if log.name == "burger")
    assert float(burger.values["calories"]) == 980


async def test_nutrition_day_bars_show_goal_eligible_trackables_without_a_target(
    session: AsyncSession,
) -> None:
    """fat_g was logged but never given a goal — it still renders as a bar (#4,
    amended: bars always show every goal-eligible trackable, matching the legacy
    TodaySummary.tsx reference; a bar's target is just None until one's set)."""
    await service.set_goals(
        session, TEST_USER, goals=[{"trackable_key": "calories", "target_value": 2200}]
    )
    await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "fat_g", "value": 20}], name="olive oil"
    )
    await session.flush()

    day = await service.get_nutrition_day(session, TEST_USER)

    bars = {b.trackable_key: b for b in day.bars}
    assert set(bars) == {"protein_g", "carbs_g", "fat_g", "fiber_g"}
    assert float(bars["fat_g"].consumed) == 20
    assert bars["fat_g"].target is None
    assert day.streak_key is None


async def test_nutrition_day_excludes_other_users_logs_and_older_days(
    session: AsyncSession,
) -> None:
    await service.log_nutrition(
        session, OTHER_USER, entries=[{"trackable_key": "calories", "value": 9999}]
    )
    yesterday = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
    await service.log_nutrition(
        session,
        TEST_USER,
        entries=[{"trackable_key": "calories", "value": 500}],
        logged_at=yesterday,
    )
    await session.flush()

    day = await service.get_nutrition_day(
        session, TEST_USER, day=datetime(2026, 8, 12, tzinfo=UTC).date()
    )

    assert float(day.hero.consumed) == 0
    assert day.logs == []


async def test_nutrition_day_calorie_hero_shows_even_with_no_goal(session: AsyncSession) -> None:
    day = await service.get_nutrition_day(session, TEST_USER)

    assert day.hero.trackable_key == "calories"
    assert day.hero.target is None
    assert float(day.hero.consumed) == 0
    bars = {b.trackable_key: b for b in day.bars}
    assert set(bars) == {"protein_g", "carbs_g", "fat_g", "fiber_g"}
    assert all(b.target is None and float(b.consumed) == 0 for b in bars.values())


async def test_save_meal_template_snapshots_items_from_existing_logs(session: AsyncSession) -> None:
    eggs = await service.log_nutrition(
        session,
        TEST_USER,
        entries=[
            {"trackable_key": "calories", "value": 180},
            {"trackable_key": "protein_g", "value": 12},
        ],
        name="2 scrambled eggs",
    )
    toast = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 90}], name="Toast"
    )
    await session.flush()

    template = await service.save_meal_template(
        session, TEST_USER, name="Usual breakfast", log_ids=[eggs.id, toast.id]
    )

    assert template.name == "Usual breakfast"
    assert [i.name for i in template.items] == ["2 scrambled eggs", "Toast"]
    assert float(template.totals["calories"]) == 270
    assert float(template.totals["protein_g"]) == 12


async def test_save_meal_template_skips_ids_belonging_to_another_user(
    session: AsyncSession,
) -> None:
    bobs_log = await service.log_nutrition(
        session,
        OTHER_USER,
        entries=[{"trackable_key": "calories", "value": 999}],
        name="Bob's food",
    )
    mine = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 100}], name="Mine"
    )
    await session.flush()

    template = await service.save_meal_template(
        session, TEST_USER, name="Mixed", log_ids=[bobs_log.id, mine.id]
    )

    assert [i.name for i in template.items] == ["Mine"]


async def test_save_meal_template_with_template_id_replaces_items(session: AsyncSession) -> None:
    a = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 100}], name="A"
    )
    b = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 200}], name="B"
    )
    await session.flush()

    first = await service.save_meal_template(session, TEST_USER, name="Draft", log_ids=[a.id])
    revised = await service.save_meal_template(
        session, TEST_USER, name="Final", log_ids=[b.id], template_id=first.id
    )

    templates = await service.list_meal_templates(session, TEST_USER)
    assert len(templates) == 1
    assert templates[0].id == first.id
    assert revised.name == "Final"
    assert [i.name for i in revised.items] == ["B"]


async def test_update_meal_template_item_replaces_name_and_values(
    session: AsyncSession,
) -> None:
    eggs = await service.log_nutrition(
        session,
        TEST_USER,
        entries=[
            {"trackable_key": "calories", "value": 180},
            {"trackable_key": "protein_g", "value": 12},
        ],
        name="2 scrambled eggs",
    )
    await session.flush()
    template = await service.save_meal_template(
        session, TEST_USER, name="Usual breakfast", log_ids=[eggs.id]
    )
    item = template.items[0]

    updated = await service.update_meal_template_item(
        session,
        TEST_USER,
        template_id=template.id,
        item_id=item.id,
        name="3 scrambled eggs",
        serving_description=None,
        values={"calories": 270, "protein_g": 18},
    )

    assert [i.name for i in updated.items] == ["3 scrambled eggs"]
    assert float(updated.items[0].values["calories"]) == 270
    assert float(updated.items[0].values["protein_g"]) == 18
    assert float(updated.totals["calories"]) == 270

    # Logging the template afterward uses the edited values, not the original ones.
    created = await service.log_meal_template(session, TEST_USER, template_id=template.id)
    values = {
        v.trackable_key: v.value
        for v in await service.get_log_values(session, TEST_USER, created[0].id)
    }
    assert float(values["calories"]) == 270


async def test_update_meal_template_item_404s_for_another_users_template(
    session: AsyncSession,
) -> None:
    eggs = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 180}], name="Eggs"
    )
    await session.flush()
    template = await service.save_meal_template(session, TEST_USER, name="Mine", log_ids=[eggs.id])

    with pytest.raises(service.NotFoundError):
        await service.update_meal_template_item(
            session,
            "someone-else",
            template_id=template.id,
            item_id=template.items[0].id,
            name="Hijacked",
            serving_description=None,
            values={},
        )


async def test_log_meal_template_writes_grouped_logs_scaled_by_multiplier(
    session: AsyncSession,
) -> None:
    eggs = await service.log_nutrition(
        session,
        TEST_USER,
        entries=[
            {"trackable_key": "calories", "value": 180},
            {"trackable_key": "protein_g", "value": 12},
        ],
        name="2 scrambled eggs",
    )
    toast = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 90}], name="Toast"
    )
    await session.flush()
    template = await service.save_meal_template(
        session, TEST_USER, name="Usual breakfast", log_ids=[eggs.id, toast.id]
    )

    created = await service.log_meal_template(
        session, TEST_USER, template_id=template.id, multiplier=1.5, meal_type="breakfast"
    )

    assert len(created) == 2
    group_ids = {log.group_id for log in created}
    assert len(group_ids) == 1
    assert all(log.group_name == "Usual breakfast" for log in created)
    assert all(log.meal_type == "breakfast" for log in created)

    eggs_copy = next(log for log in created if log.name == "2 scrambled eggs")
    values = {
        v.trackable_key: v.value
        for v in await service.get_log_values(session, TEST_USER, eggs_copy.id)
    }
    assert float(values["calories"]) == 270  # 180 * 1.5
    assert float(values["protein_g"]) == 18  # 12 * 1.5

    # The template's own snapshot is untouched by scaling the logged instance.
    templates = await service.list_meal_templates(session, TEST_USER)
    assert float(templates[0].totals["calories"]) == 270  # 180 + 90, unscaled


async def test_nutrition_day_collapses_a_logged_template_into_one_grouped_entry(
    session: AsyncSession,
) -> None:
    eggs = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 180}], name="Eggs"
    )
    toast = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 90}], name="Toast"
    )
    await session.flush()
    template = await service.save_meal_template(
        session, TEST_USER, name="Usual breakfast", log_ids=[eggs.id, toast.id]
    )
    await service.log_meal_template(session, TEST_USER, template_id=template.id)
    await session.flush()

    day = await service.get_nutrition_day(session, TEST_USER)

    grouped = [entry for entry in day.logs if entry.items]
    assert len(grouped) == 1
    assert grouped[0].name == "Usual breakfast"
    assert float(grouped[0].values["calories"]) == 270
    assert {item.name for item in grouped[0].items} == {"Eggs", "Toast"}
    # the two ungrouped logs used to build the template are still their own entries
    assert len([entry for entry in day.logs if not entry.items]) == 2
    assert len(day.templates) == 1


async def test_delete_meal_template_removes_it_and_is_scoped_to_owner(
    session: AsyncSession,
) -> None:
    a = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 100}], name="A"
    )
    await session.flush()
    template = await service.save_meal_template(session, TEST_USER, name="Solo", log_ids=[a.id])

    with pytest.raises(service.NotFoundError):
        await service.delete_meal_template(session, OTHER_USER, template.id)

    await service.delete_meal_template(session, TEST_USER, template.id)
    await session.flush()

    assert await service.list_meal_templates(session, TEST_USER) == []
