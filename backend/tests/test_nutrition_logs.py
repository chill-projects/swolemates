from datetime import UTC, datetime

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
