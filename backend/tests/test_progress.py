from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import nutrition as nutrition_service
from app.services import progress as service
from app.services import workouts as workouts_service
from tests.conftest import TEST_USER


async def test_get_progress_workouts_focus_excludes_nutrition(session: AsyncSession) -> None:
    await workouts_service.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "Deadlift", "sets": [{"weight": 300, "reps": 3}]}],
        logged_at=datetime(2026, 8, 10, tzinfo=UTC),
    )

    progress = await service.get_progress(
        session, TEST_USER, focus="workouts", as_of=date(2026, 8, 10)
    )

    assert progress.nutrition is None
    assert progress.workouts is not None
    assert progress.workouts.streak.this_week == 1


async def test_get_progress_nutrition_focus_excludes_workouts(session: AsyncSession) -> None:
    await nutrition_service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 2000}]
    )

    progress = await service.get_progress(session, TEST_USER, focus="nutrition")

    assert progress.workouts is None
    assert progress.nutrition is not None
    assert progress.nutrition.streak == 1


async def test_get_progress_all_focus_populates_both(session: AsyncSession) -> None:
    progress = await service.get_progress(session, TEST_USER, focus="all")

    assert progress.workouts is not None
    assert progress.nutrition is not None


async def test_get_progress_recent_prs_excludes_ones_outside_the_window(
    session: AsyncSession,
) -> None:
    await workouts_service.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "Deadlift", "sets": [{"weight": 300, "reps": 3}]}],
        logged_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    await workouts_service.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "Barbell Bench Press", "sets": [{"weight": 185, "reps": 5}]}],
        logged_at=datetime(2026, 8, 10, tzinfo=UTC),
    )

    progress = await service.get_progress(
        session, TEST_USER, focus="workouts", period="week", as_of=date(2026, 8, 10)
    )

    names = {pr.exercise_name for pr in progress.workouts.recent_prs}
    assert names == {"Barbell Bench Press"}


async def test_get_progress_trend_rising_across_two_sessions(session: AsyncSession) -> None:
    await workouts_service.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "Deadlift", "sets": [{"weight": 300, "reps": 3}]}],
        logged_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    await workouts_service.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "Deadlift", "sets": [{"weight": 310, "reps": 3}]}],
        logged_at=datetime(2026, 8, 8, tzinfo=UTC),
    )

    progress = await service.get_progress(
        session, TEST_USER, focus="workouts", period="month", as_of=date(2026, 8, 8)
    )

    trend = next(t for t in progress.workouts.trends if t.exercise_name == "Deadlift")
    assert trend.direction == "rising"
    assert float(trend.latest_weight) == 310
    assert float(trend.previous_weight) == 300


async def test_get_progress_trend_falling_across_two_sessions(session: AsyncSession) -> None:
    await workouts_service.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "Deadlift", "sets": [{"weight": 310, "reps": 3}]}],
        logged_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    await workouts_service.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "Deadlift", "sets": [{"weight": 300, "reps": 3}]}],
        logged_at=datetime(2026, 8, 8, tzinfo=UTC),
    )

    progress = await service.get_progress(
        session, TEST_USER, focus="workouts", period="month", as_of=date(2026, 8, 8)
    )

    trend = next(t for t in progress.workouts.trends if t.exercise_name == "Deadlift")
    assert trend.direction == "falling"


async def test_get_progress_trend_flat_across_two_sessions(session: AsyncSession) -> None:
    for d in (1, 8):
        await workouts_service.log_workout(
            session,
            TEST_USER,
            exercises=[{"exercise": "Deadlift", "sets": [{"weight": 300, "reps": 3}]}],
            logged_at=datetime(2026, 8, d, tzinfo=UTC),
        )

    progress = await service.get_progress(
        session, TEST_USER, focus="workouts", period="month", as_of=date(2026, 8, 8)
    )

    trend = next(t for t in progress.workouts.trends if t.exercise_name == "Deadlift")
    assert trend.direction == "flat"


async def test_get_progress_trend_omitted_for_a_single_session_exercise(
    session: AsyncSession,
) -> None:
    await workouts_service.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "Deadlift", "sets": [{"weight": 300, "reps": 3}]}],
        logged_at=datetime(2026, 8, 8, tzinfo=UTC),
    )

    progress = await service.get_progress(
        session, TEST_USER, focus="workouts", period="month", as_of=date(2026, 8, 8)
    )

    assert progress.workouts.trends == []


async def test_get_progress_adherence_is_none_without_a_calorie_goal(
    session: AsyncSession,
) -> None:
    await nutrition_service.log_nutrition(
        session, TEST_USER, entries=[{"trackable_key": "calories", "value": 2000}]
    )

    progress = await service.get_progress(
        session, TEST_USER, focus="nutrition", as_of=date(2026, 8, 8)
    )

    assert progress.nutrition.adherence_pct is None


async def test_get_progress_adherence_pct_counts_hit_vs_miss_days_with_a_goal(
    session: AsyncSession,
) -> None:
    await nutrition_service.set_goals(
        session, TEST_USER, goals=[{"trackable_key": "calories", "target_value": 2000}]
    )
    await nutrition_service.log_nutrition(
        session,
        TEST_USER,
        entries=[{"trackable_key": "calories", "value": 1900}],
        logged_at=datetime(2026, 8, 7, tzinfo=UTC),
    )
    await nutrition_service.log_nutrition(
        session,
        TEST_USER,
        entries=[{"trackable_key": "calories", "value": 3000}],
        logged_at=datetime(2026, 8, 8, tzinfo=UTC),
    )

    progress = await service.get_progress(
        session, TEST_USER, focus="nutrition", period="week", as_of=date(2026, 8, 8)
    )

    assert progress.nutrition.hit_days == 1
    assert progress.nutrition.total_days == 2
    assert progress.nutrition.adherence_pct == 50.0


async def test_get_progress_adherence_excludes_no_data_days(session: AsyncSession) -> None:
    await nutrition_service.set_goals(
        session, TEST_USER, goals=[{"trackable_key": "calories", "target_value": 2000}]
    )
    await nutrition_service.log_nutrition(
        session,
        TEST_USER,
        entries=[{"trackable_key": "calories", "value": 1900}],
        logged_at=datetime(2026, 8, 8, tzinfo=UTC),
    )

    progress = await service.get_progress(
        session, TEST_USER, focus="nutrition", period="week", as_of=date(2026, 8, 8)
    )

    assert progress.nutrition.total_days == 1
    assert progress.nutrition.adherence_pct == 100.0


async def test_get_progress_trend_ignores_warmup_and_timed_only_sessions(
    session: AsyncSession,
) -> None:
    await workouts_service.log_workout(
        session,
        TEST_USER,
        exercises=[
            {
                "exercise": "Deadlift",
                "sets": [{"weight": 135, "reps": 8, "is_warmup": True}],
            }
        ],
        logged_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    await workouts_service.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "Deadlift", "sets": [{"weight": 300, "reps": 3}]}],
        logged_at=datetime(2026, 8, 8, tzinfo=UTC),
    )

    progress = await service.get_progress(
        session, TEST_USER, focus="workouts", period="month", as_of=date(2026, 8, 8)
    )

    assert progress.workouts.trends == []
