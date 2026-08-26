from datetime import UTC, date, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import nutrition as service
from tests.conftest import OTHER_USER, TEST_USER


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


async def test_nutrition_day_bars_exclude_weight_even_with_a_goal_and_logs(
    session: AsyncSession,
) -> None:
    """weight_lbs is goal-eligible (#19, resolved) but deliberately excluded from
    the day's macro bars — its progress belongs in its own progress-bar/graph
    framing, not mixed in with Protein/Carbs/Fat/Fiber."""
    await service.set_goals(
        session, TEST_USER, goals=[{"trackable_key": "weight_lbs", "target_value": 140}]
    )
    await service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "weight_lbs", "value": 150}]
    )
    await session.flush()

    day = await service.get_nutrition_day(session, TEST_USER)

    assert "weight_lbs" not in {b.trackable_key for b in day.bars}


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


async def test_nutrition_day_tz_offset_finds_a_log_made_after_local_midnight_but_before_utcs(
    session: AsyncSession,
) -> None:
    """Regression: a log made at 8pm Pacific — already the next UTC calendar day — must
    still show up under the caller's local "today" once the caller's UTC offset is
    supplied. Passing `day` alone (the earlier, incomplete fix) doesn't cover this: the
    naive UTC-bounded window for "2026-08-25" ends before this log's UTC timestamp even
    starts.
    """
    pacific_8pm_in_utc = datetime(2026, 8, 26, 3, 0, tzinfo=UTC)  # 2026-08-25 20:00 PDT
    await service.log_nutrition(
        session,
        TEST_USER,
        entries=[{"trackable_key": "calories", "value": 450}],
        logged_at=pacific_8pm_in_utc,
    )
    await session.flush()

    utc_only = await service.get_nutrition_day(session, TEST_USER, day=date(2026, 8, 25))
    assert float(utc_only.hero.consumed) == 0

    local_aware = await service.get_nutrition_day(
        session, TEST_USER, day=date(2026, 8, 25), tz_offset_minutes=420
    )
    assert float(local_aware.hero.consumed) == 450


async def test_nutrition_day_calorie_hero_shows_even_with_no_goal(session: AsyncSession) -> None:
    day = await service.get_nutrition_day(session, TEST_USER)

    assert day.hero.trackable_key == "calories"
    assert day.hero.target is None
    assert float(day.hero.consumed) == 0
    bars = {b.trackable_key: b for b in day.bars}
    assert set(bars) == {"protein_g", "carbs_g", "fat_g", "fiber_g"}
    assert all(b.target is None and float(b.consumed) == 0 for b in bars.values())


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
