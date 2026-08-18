from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import GoalType
from app.services import nutrition as service
from app.services import profile as profile_service
from tests.conftest import OTHER_USER, TEST_USER


async def test_calendar_day_with_no_logs_is_no_data(session: AsyncSession) -> None:
    days = await service.get_nutrition_calendar(
        session, TEST_USER, start=date(2026, 8, 10), end=date(2026, 8, 10)
    )

    assert len(days) == 1
    assert days[0].status == "no-data"
    assert float(days[0].hero.consumed) == 0


async def test_calendar_day_hit_with_no_target_set(session: AsyncSession) -> None:
    """Matches legacy's dayStatus(): logging with no target set is always a "hit" —
    a pure "did you log" signal, not a goal check."""
    await service.log_nutrition(
        session,
        TEST_USER,
        entries=[{"trackable_key": "calories", "value": 500}],
        logged_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
    )
    await session.flush()

    days = await service.get_nutrition_calendar(
        session, TEST_USER, start=date(2026, 8, 10), end=date(2026, 8, 10)
    )

    assert days[0].status == "hit"


async def test_calendar_deficit_goal_never_fails_for_eating_less(session: AsyncSession) -> None:
    await profile_service.update_profile(session, TEST_USER, goal_type=GoalType.lose_weight)
    await service.set_goals(
        session, TEST_USER, goals=[{"trackable_key": "calories", "target_value": 2000}]
    )
    await service.log_nutrition(
        session,
        TEST_USER,
        entries=[{"trackable_key": "calories", "value": 1200}],
        logged_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
    )
    await session.flush()

    days = await service.get_nutrition_calendar(
        session, TEST_USER, start=date(2026, 8, 10), end=date(2026, 8, 10)
    )

    assert days[0].status == "hit"


async def test_calendar_deficit_goal_misses_past_the_5_percent_grace_window(
    session: AsyncSession,
) -> None:
    await profile_service.update_profile(session, TEST_USER, goal_type=GoalType.lose_weight)
    await service.set_goals(
        session, TEST_USER, goals=[{"trackable_key": "calories", "target_value": 2000}]
    )
    await service.log_nutrition(
        session,
        TEST_USER,
        entries=[{"trackable_key": "calories", "value": 2200}],
        logged_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
    )
    await session.flush()

    days = await service.get_nutrition_calendar(
        session, TEST_USER, start=date(2026, 8, 10), end=date(2026, 8, 10)
    )

    assert days[0].status == "miss"


async def test_calendar_surplus_goal_never_fails_for_eating_more(session: AsyncSession) -> None:
    await profile_service.update_profile(session, TEST_USER, goal_type=GoalType.gain_muscle)
    await service.set_goals(
        session, TEST_USER, goals=[{"trackable_key": "calories", "target_value": 2500}]
    )
    await service.log_nutrition(
        session,
        TEST_USER,
        entries=[{"trackable_key": "calories", "value": 3000}],
        logged_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
    )
    await session.flush()

    days = await service.get_nutrition_calendar(
        session, TEST_USER, start=date(2026, 8, 10), end=date(2026, 8, 10)
    )

    assert days[0].status == "hit"


async def test_calendar_maintain_goal_uses_symmetric_band(session: AsyncSession) -> None:
    await profile_service.update_profile(session, TEST_USER, goal_type=GoalType.maintain)
    await service.set_goals(
        session, TEST_USER, goals=[{"trackable_key": "calories", "target_value": 2000}]
    )
    await service.log_nutrition(
        session,
        TEST_USER,
        entries=[{"trackable_key": "calories", "value": 2300}],
        logged_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
    )
    await session.flush()

    days = await service.get_nutrition_calendar(
        session, TEST_USER, start=date(2026, 8, 10), end=date(2026, 8, 10)
    )

    assert days[0].status == "miss"


async def test_calendar_excludes_other_users_and_out_of_range_days(session: AsyncSession) -> None:
    await service.log_nutrition(
        session,
        OTHER_USER,
        entries=[{"trackable_key": "calories", "value": 9999}],
        logged_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
    )
    await service.log_nutrition(
        session,
        TEST_USER,
        entries=[{"trackable_key": "calories", "value": 500}],
        logged_at=datetime(2026, 8, 9, 12, tzinfo=UTC),
    )
    await session.flush()

    days = await service.get_nutrition_calendar(
        session, TEST_USER, start=date(2026, 8, 10), end=date(2026, 8, 12)
    )

    assert [d.date for d in days] == [date(2026, 8, 10), date(2026, 8, 11), date(2026, 8, 12)]
    assert all(d.status == "no-data" for d in days)


async def test_calendar_hero_and_bars_match_get_nutrition_day_shape(session: AsyncSession) -> None:
    await service.set_goals(
        session,
        TEST_USER,
        goals=[
            {"trackable_key": "calories", "target_value": 2200},
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
        logged_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
    )
    await session.flush()

    days = await service.get_nutrition_calendar(
        session, TEST_USER, start=date(2026, 8, 10), end=date(2026, 8, 10)
    )

    day = days[0]
    assert float(day.hero.consumed) == 450
    assert float(day.hero.target) == 2200
    bars = {b.trackable_key: b for b in day.bars}
    assert set(bars) == {"protein_g", "carbs_g", "fat_g", "fiber_g"}
    assert float(bars["protein_g"].consumed) == 32
    assert float(bars["protein_g"].target) == 160
