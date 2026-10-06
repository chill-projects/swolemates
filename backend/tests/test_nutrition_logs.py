from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import nutrition as service
from app.services.timezones import parse_local_datetime
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


async def test_delete_nutrition_log_over_rest(client: AsyncClient) -> None:
    logged = await client.post(
        "/api/nutrition/logs",
        json={"entries": [{"trackable_key": "calories", "value": "150"}], "name": "Yogurt"},
    )
    log_id = logged.json()["id"]

    deleted = await client.delete(f"/api/nutrition/logs/{log_id}")
    assert deleted.status_code == 204

    day = await client.get("/api/nutrition/day")
    assert log_id not in [entry["id"] for entry in day.json()["logs"]]


async def test_delete_nutrition_log_404s_for_unknown_log(client: AsyncClient) -> None:
    resp = await client.delete(f"/api/nutrition/logs/{uuid4()}")
    assert resp.status_code == 404


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


async def test_log_nutrition_rounds_float_noise(session: AsyncSession) -> None:
    """External sources (e.g. search_food_facts scaling Open Food Facts to a
    serving) can hand back ~15-digit float noise like 3.90000009536743; stored
    values should come out clean regardless."""
    log = await service.log_nutrition(
        session,
        TEST_USER,
        entries=[
            {"trackable_key": "calories", "value": 149.500001},
            {"trackable_key": "protein_g", "value": 3.90000009536743},
            {"trackable_key": "fiber_g", "value": 0.119999997317791},
        ],
    )
    await session.flush()

    values = await service.get_log_values(session, TEST_USER, log.id)
    by_key = {v.trackable_key: v.value for v in values}

    assert by_key["calories"] == 150
    assert by_key["protein_g"] == Decimal("3.9")
    assert by_key["fiber_g"] == Decimal("0.1")


async def test_update_nutrition_log_rounds_float_noise(session: AsyncSession) -> None:
    log = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "protein_g", "value": 10}]
    )
    await session.flush()

    await service.update_nutrition_log(
        session, TEST_USER, log_id=log.id, values={"protein_g": 12.6999998092651}
    )

    values = await service.get_log_values(session, TEST_USER, log.id)
    assert values[0].value == Decimal("12.7")


async def test_users_cannot_read_each_others_log_values(session: AsyncSession) -> None:
    """The whole permission model, asserted directly against the service layer."""
    bobs_log = await service.log_nutrition(
        session, OTHER_USER, entries=[{"trackable_key": "calories", "value": 999}]
    )
    await session.flush()

    assert await service.get_log_values(session, TEST_USER, bobs_log.id) == []


async def test_delete_nutrition_log_removes_it(session: AsyncSession) -> None:
    log = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 150}], name="Yogurt"
    )
    await session.flush()

    await service.delete_nutrition_log(session, TEST_USER, log.id)

    assert await service.get_log_values(session, TEST_USER, log.id) == []


async def test_delete_nutrition_log_404s_for_another_users_log(session: AsyncSession) -> None:
    bobs_log = await service.log_nutrition(
        session, OTHER_USER, entries=[{"trackable_key": "calories", "value": 999}]
    )
    await session.flush()

    with pytest.raises(service.NotFoundError):
        await service.delete_nutrition_log(session, TEST_USER, bobs_log.id)


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


async def _template_logged_meal(session: AsyncSession) -> tuple[object, object]:
    """Logs a saved meal, returning (group_id the day view shows, its logs). A
    template writes one Log per item sharing a group_id, and the day view collapses
    them into a single row keyed by that group_id — so the id the UI hands back for
    the row is not any Log.id."""
    item = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 51}], name="Coffee"
    )
    await session.flush()
    template = await service.save_meal_template(
        session, TEST_USER, name="Protein coffee", log_ids=[item.id]
    )
    logs = await service.log_meal_template(session, TEST_USER, template_id=template.id)
    await session.flush()
    return logs[0].group_id, logs


async def test_update_nutrition_log_tags_a_whole_template_logged_meal(
    session: AsyncSession,
) -> None:
    """The day row's id is the group_id — editing through it used to 404, so a
    saved-meal entry couldn't be tagged at all."""
    group_id, logs = await _template_logged_meal(session)

    await service.update_nutrition_log(session, TEST_USER, log_id=group_id, meal_type="breakfast")

    day = await service.get_nutrition_day(session, TEST_USER)
    row = next(entry for entry in day.logs if entry.id == group_id)
    assert row.meal_type == "breakfast"
    assert all(log.meal_type == "breakfast" for log in logs)


async def test_update_nutrition_log_renames_a_group_via_its_snapshot_name(
    session: AsyncSession,
) -> None:
    group_id, logs = await _template_logged_meal(session)

    await service.update_nutrition_log(session, TEST_USER, log_id=group_id, name="Morning coffee")

    day = await service.get_nutrition_day(session, TEST_USER)
    row = next(entry for entry in day.logs if entry.id == group_id)
    assert row.name == "Morning coffee"
    # The item keeps its own name; only the group's snapshot changed.
    assert all(log.name == "Coffee" for log in logs)


async def test_update_nutrition_log_rejects_values_on_a_group(session: AsyncSession) -> None:
    group_id, _ = await _template_logged_meal(session)

    with pytest.raises(ValueError, match="separate items"):
        await service.update_nutrition_log(
            session, TEST_USER, log_id=group_id, values={"calories": 10}
        )


async def test_delete_nutrition_log_removes_a_whole_template_logged_meal(
    session: AsyncSession,
) -> None:
    group_id, logs = await _template_logged_meal(session)

    await service.delete_nutrition_log(session, TEST_USER, group_id)

    day = await service.get_nutrition_day(session, TEST_USER)
    assert all(entry.id != group_id for entry in day.logs)
    assert float(day.hero.consumed) == 51  # only the original single log is left


async def test_update_nutrition_log_404s_for_another_users_group(session: AsyncSession) -> None:
    item = await service.log_nutrition(
        session, OTHER_USER, entries=[{"trackable_key": "calories", "value": 51}], name="Coffee"
    )
    await session.flush()
    template = await service.save_meal_template(
        session, OTHER_USER, name="Bob's coffee", log_ids=[item.id]
    )
    logs = await service.log_meal_template(session, OTHER_USER, template_id=template.id)
    await session.flush()

    with pytest.raises(service.NotFoundError):
        await service.update_nutrition_log(
            session, TEST_USER, log_id=logs[0].group_id, meal_type="breakfast"
        )


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


async def test_weight_history_returns_weigh_ins_oldest_first(client: AsyncClient) -> None:
    """Ordered by `logged_at`, not insertion order — these go in newest-first to make
    sure the endpoint sorts rather than echoing the write order back."""
    for logged_at, value in [
        ("2026-08-25T08:00:00Z", 149),
        ("2026-08-04T08:00:00Z", 152),
        ("2026-08-11T08:00:00Z", 151),
    ]:
        await client.post(
            "/api/nutrition/logs",
            json={
                "entries": [{"trackable_key": "weight_lbs", "value": value}],
                "logged_at": logged_at,
            },
        )

    resp = await client.get("/api/nutrition/weights")

    assert resp.status_code == 200
    body = resp.json()
    assert [float(w["weight_lbs"]) for w in body] == [152, 151, 149]


async def test_weight_history_excludes_food_logs(client: AsyncClient) -> None:
    await client.post(
        "/api/nutrition/logs",
        json={"entries": [{"trackable_key": "calories", "value": 500}]},
    )

    resp = await client.get("/api/nutrition/weights")

    assert resp.json() == []


async def test_log_nutrition_backdates_to_a_day_that_went_unlogged(session: AsyncSession) -> None:
    """The gap this whole feature exists for: food remembered a day late has to land on
    the day it was eaten, not the day it was typed in."""
    la = ZoneInfo("America/Los_Angeles")
    monday = date(2026, 9, 7)

    await service.log_nutrition(
        session,
        TEST_USER,
        entries=[{"trackable_key": "calories", "value": 620}],
        name="Monday's dinner",
        logged_at=parse_local_datetime("2026-09-07T19:30", la),
    )

    day = await service.get_nutrition_day(session, TEST_USER, day=monday, tz=la)
    assert [entry.name for entry in day.logs] == ["Monday's dinner"]
    assert day.hero.consumed == Decimal(620)

    tuesday = await service.get_nutrition_day(
        session, TEST_USER, day=monday + timedelta(days=1), tz=la
    )
    assert tuesday.logs == []


async def test_backdating_a_late_evening_meal_lands_on_the_local_day(
    session: AsyncSession,
) -> None:
    """7:30pm Pacific is already the next day in UTC. The meal belongs to the local
    day the user named, not the one the raw instant falls on."""
    la = ZoneInfo("America/Los_Angeles")
    when = parse_local_datetime("2026-09-07T19:30", la)
    assert when.astimezone(UTC).date() == date(2026, 9, 8)

    await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 400}], logged_at=when
    )

    assert await service.get_nutrition_day(session, TEST_USER, day=date(2026, 9, 7), tz=la)
    assert not (
        await service.get_nutrition_day(session, TEST_USER, day=date(2026, 9, 8), tz=la)
    ).logs


async def test_update_nutrition_log_moves_an_entry_to_another_day(
    session: AsyncSession,
) -> None:
    log = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 300}], name="Dinner"
    )
    yesterday = datetime(2026, 9, 9, 19, 0, tzinfo=UTC)

    await service.update_nutrition_log(session, TEST_USER, log_id=log.id, logged_at=yesterday)

    assert log.logged_at == yesterday
    assert log.edited_by_user is True


async def test_update_nutrition_log_moves_a_saved_meals_items_together(
    session: AsyncSession,
) -> None:
    """A group is one row in the day view, so a half-moved group would show the same
    meal on two days at once."""
    first = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 200}], name="Yogurt"
    )
    second = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 100}], name="Granola"
    )
    template = await service.save_meal_template(
        session, TEST_USER, name="Usual breakfast", log_ids=[first.id, second.id]
    )
    logs = await service.log_meal_template(session, TEST_USER, template_id=template.id)
    group_id = logs[0].group_id
    moved_to = datetime(2026, 9, 9, 8, 0, tzinfo=UTC)

    await service.update_nutrition_log(session, TEST_USER, log_id=group_id, logged_at=moved_to)

    assert {entry.logged_at for entry in logs} == {moved_to}


async def test_amend_last_log_treats_a_date_as_a_correction_not_an_undo(
    session: AsyncSession,
) -> None:
    """ "Actually that was yesterday" must patch the entry. Reading a date-only amend
    as "no fields given" would delete the thing the user was trying to keep."""
    log = await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 500}], name="Burrito"
    )
    yesterday = datetime(2026, 9, 9, 13, 0, tzinfo=UTC)

    updated, log_id, _name = await service.amend_last_log(session, TEST_USER, logged_at=yesterday)

    assert updated is not None
    assert log_id == log.id
    assert updated.logged_at == yesterday


async def test_patch_nutrition_log_moves_the_day_over_rest(client: AsyncClient) -> None:
    logged = await client.post(
        "/api/nutrition/logs",
        json={"entries": [{"trackable_key": "calories", "value": "250"}], "name": "Toast"},
    )
    log_id = logged.json()["id"]

    resp = await client.patch(
        f"/api/nutrition/logs/{log_id}", json={"logged_at": "2026-09-07T08:00:00Z"}
    )

    assert resp.status_code == 200
    assert resp.json()["logged_at"].startswith("2026-09-07T08:00")
    today = await client.get("/api/nutrition/day")
    assert log_id not in [entry["id"] for entry in today.json()["logs"]]
    moved_to = await client.get("/api/nutrition/day", params={"day": "2026-09-07"})
    assert log_id in [entry["id"] for entry in moved_to.json()["logs"]]
