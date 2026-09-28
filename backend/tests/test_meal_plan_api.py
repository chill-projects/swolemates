"""The meal plan's REST surface.

Thin by design — the router has no logic of its own, so what's worth testing here is
the wiring: that each verb reaches the right service call, that a service ValueError
becomes a 400 and a NotFoundError a 404, and that the response shape matches what the
Plan tab actually renders.
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient


async def _saved_meal(client: AsyncClient, name: str, calories: str = "600") -> str:
    logged = await client.post(
        "/api/nutrition/logs",
        json={
            "entries": [
                {"trackable_key": "calories", "value": calories},
                {"trackable_key": "protein_g", "value": "40"},
            ],
            "name": name,
        },
    )
    saved = await client.post(
        "/api/nutrition/templates", json={"name": name, "log_ids": [logged.json()["id"]]}
    )
    return saved.json()["id"]


async def test_plan_edit_log_and_clear_round_trip(client: AsyncClient) -> None:
    template_id = await _saved_meal(client, "Steak", calories="720")

    planned = await client.post(
        "/api/meal-plan",
        json={"scheduled_for": "2026-09-28", "meal_type": "dinner", "template_id": template_id},
    )
    assert planned.status_code == 201
    body = planned.json()
    assert body["name"] == "Steak"
    assert body["source"] == "template"
    assert body["values"]["calories"] == "720"
    assert body["estimated"] is True
    meal_id = body["id"]

    week = await client.get("/api/meal-plan", params={"start": "2026-09-28", "end": "2026-09-30"})
    assert week.status_code == 200
    days = week.json()
    assert [d["scheduled_for"] for d in days] == ["2026-09-28", "2026-09-29", "2026-09-30"]
    assert days[0]["totals"]["calories"] == "720"
    assert days[0]["unestimated"] == 0

    edited = await client.patch(
        f"/api/meal-plan/{meal_id}", json={"values": {"calories": "650"}, "name": "Steak, smaller"}
    )
    assert edited.status_code == 200
    assert edited.json()["values"]["calories"] == "650"
    assert edited.json()["overridden"] is True
    assert edited.json()["name"] == "Steak, smaller"

    logged = await client.post(f"/api/meal-plan/{meal_id}/log")
    assert logged.status_code == 200
    assert logged.json()["status"] == "logged"

    cleared = await client.delete(f"/api/meal-plan/{meal_id}")
    assert cleared.status_code == 204
    after = await client.get("/api/meal-plan", params={"start": "2026-09-28", "end": "2026-09-28"})
    assert after.json()[0]["meals"] == []


async def test_an_ad_hoc_meal_reports_itself_as_unestimated(client: AsyncClient) -> None:
    planned = await client.post(
        "/api/meal-plan",
        json={"scheduled_for": "2026-09-28", "meal_type": "dinner", "name": "Dinner at Mum's"},
    )
    assert planned.status_code == 201
    assert planned.json()["estimated"] is False
    assert planned.json()["values"] == {}

    week = await client.get("/api/meal-plan", params={"start": "2026-09-28", "end": "2026-09-28"})
    assert week.json()[0]["unestimated"] == 1
    assert week.json()[0]["totals"] == {}


async def test_logging_a_meal_with_no_macros_is_a_400(client: AsyncClient) -> None:
    planned = await client.post(
        "/api/meal-plan",
        json={"scheduled_for": "2026-09-28", "meal_type": "dinner", "name": "Dinner at Mum's"},
    )
    resp = await client.post(f"/api/meal-plan/{planned.json()['id']}/log")
    assert resp.status_code == 400
    assert "no macros" in resp.json()["detail"]


async def test_an_unknown_meal_type_is_a_400(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/meal-plan",
        json={"scheduled_for": "2026-09-28", "meal_type": "brunch", "name": "Eggs"},
    )
    assert resp.status_code == 400


@pytest.mark.parametrize("verb", ["patch", "delete", "log"])
async def test_unknown_planned_meal_is_a_404(client: AsyncClient, verb: str) -> None:
    missing = uuid4()
    if verb == "patch":
        resp = await client.patch(f"/api/meal-plan/{missing}", json={"name": "x"})
    elif verb == "delete":
        resp = await client.delete(f"/api/meal-plan/{missing}")
    else:
        resp = await client.post(f"/api/meal-plan/{missing}/log")
    assert resp.status_code == 404


async def test_kitchen_round_trips(client: AsyncClient) -> None:
    slaw_id = await _saved_meal(client, "Cabbage slaw")

    leftover = await client.post(
        "/api/kitchen",
        json={
            "kind": "leftover",
            "name": "Chicken curry",
            "portion": "0.5",
            "values": {"calories": "780", "protein_g": "48"},
        },
    )
    assert leftover.status_code == 201
    assert leftover.json()["values"]["calories"] == "390"

    ingredient = await client.post(
        "/api/kitchen",
        json={"kind": "ingredient", "name": "Half a cabbage", "template_ids": [slaw_id]},
    )
    assert ingredient.status_code == 201
    assert ingredient.json()["values"] == {}
    assert [t["name"] for t in ingredient.json()["templates"]] == ["Cabbage slaw"]

    listed = await client.get("/api/kitchen")
    assert {i["name"] for i in listed.json()} == {"Chicken curry", "Half a cabbage"}

    planned = await client.post(
        "/api/meal-plan",
        json={
            "scheduled_for": "2026-09-28",
            "meal_type": "dinner",
            "kitchen_item_id": leftover.json()["id"],
        },
    )
    assert planned.json()["source"] == "leftover"
    assert planned.json()["values"]["calories"] == "390"

    removed = await client.delete(f"/api/kitchen/{leftover.json()['id']}")
    assert removed.status_code == 204
    assert [i["name"] for i in (await client.get("/api/kitchen")).json()] == ["Half a cabbage"]

    # The plan that used it keeps its numbers.
    week = await client.get("/api/meal-plan", params={"start": "2026-09-28", "end": "2026-09-28"})
    assert week.json()[0]["meals"][0]["values"]["calories"] == "390"


async def test_planning_an_ingredient_is_a_400(client: AsyncClient) -> None:
    item = await client.post(
        "/api/kitchen", json={"kind": "ingredient", "name": "Half a cabbage"}
    )
    resp = await client.post(
        "/api/meal-plan",
        json={
            "scheduled_for": "2026-09-28",
            "meal_type": "dinner",
            "kitchen_item_id": item.json()["id"],
        },
    )
    assert resp.status_code == 400
    assert "ingredient" in resp.json()["detail"]


async def test_meal_plan_requires_a_sane_range(client: AsyncClient) -> None:
    resp = await client.get("/api/meal-plan", params={"start": "2026-09-30", "end": "2026-09-28"})
    assert resp.status_code == 400
