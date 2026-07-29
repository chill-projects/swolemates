import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import tmpx as service
from tests.conftest import OTHER_USER, TEST_USER


async def test_health_does_not_require_a_database(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_create_then_list(client: AsyncClient) -> None:
    created = await client.post("/api/tmpx", json={"name": "squat", "value": 225})
    assert created.status_code == 201

    listed = await client.get("/api/tmpx")
    assert [i["name"] for i in listed.json()] == ["squat"]


async def test_users_cannot_see_each_others_items(session: AsyncSession) -> None:
    """The whole permission model, asserted directly against the service layer."""
    await service.add_item(session, OTHER_USER, name="bob's secret")
    await session.flush()

    assert await service.list_items(session, TEST_USER) == []
    assert [i.name for i in await service.list_items(session, OTHER_USER)] == ["bob's secret"]


async def test_fetching_another_users_item_by_id_is_a_404(session: AsyncSession) -> None:
    """Not a 403 — distinguishing the two would confirm the row exists."""
    item = await service.add_item(session, OTHER_USER, name="bob's secret")
    await session.flush()

    with pytest.raises(service.NotFoundError):
        await service.get_item(session, TEST_USER, item.id)


async def test_deleting_another_users_item_is_refused(session: AsyncSession) -> None:
    item = await service.add_item(session, OTHER_USER, name="bob's secret")
    await session.flush()

    with pytest.raises(service.NotFoundError):
        await service.delete_item(session, TEST_USER, item.id)

    assert len(await service.list_items(session, OTHER_USER)) == 1


async def test_blank_name_is_rejected(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="name must not be empty"):
        await service.add_item(session, TEST_USER, name="   ")
