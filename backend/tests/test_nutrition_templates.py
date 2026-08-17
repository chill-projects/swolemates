from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import nutrition as service
from tests.conftest import OTHER_USER, TEST_USER


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
