from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workouts import PersonalRecord, PersonalRecordKind, WorkoutSet
from app.services import celebrations as service
from app.services import planned_workouts as planned_service
from app.services import workout_templates as templates
from app.services import workouts
from tests.conftest import OTHER_USER, TEST_USER


async def _pr_value(session: AsyncSession, user: str, exercise_id, kind: PersonalRecordKind):
    result = await session.execute(
        select(PersonalRecord).where(
            PersonalRecord.user_id == user,
            PersonalRecord.exercise_id == exercise_id,
            PersonalRecord.kind == kind,
        )
    )
    pr = result.scalar_one_or_none()
    return pr.value if pr else None


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _at(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 12, tzinfo=UTC)


async def test_log_set_celebrates_a_new_weight_and_e1rm_pr(session: AsyncSession) -> None:
    result = await workouts.log_set(session, TEST_USER, exercise="Deadlift", reps=5, weight=225)

    kinds = {c.kind for c in result.workout.celebrations}
    assert kinds == {"weight", "e1rm"}
    assert all(c.previous is None for c in result.workout.celebrations)


async def test_log_set_does_not_celebrate_a_tied_weight(session: AsyncSession) -> None:
    await workouts.log_set(session, TEST_USER, exercise="Deadlift", reps=5, weight=225)

    result = await workouts.log_set(session, TEST_USER, exercise="Deadlift", reps=5, weight=225)

    assert result.workout.celebrations == []


async def test_log_set_does_not_celebrate_a_lower_weight(session: AsyncSession) -> None:
    await workouts.log_set(session, TEST_USER, exercise="Deadlift", reps=5, weight=225)

    result = await workouts.log_set(session, TEST_USER, exercise="Deadlift", reps=5, weight=185)

    assert result.workout.celebrations == []


async def test_log_set_excludes_warmup_sets(session: AsyncSession) -> None:
    result = await workouts.log_set(
        session, TEST_USER, exercise="Deadlift", reps=5, weight=500, is_warmup=True
    )

    assert result.workout.celebrations == []


async def test_log_set_excludes_timed_sets(session: AsyncSession) -> None:
    result = await workouts.log_set(
        session, TEST_USER, exercise="Plank", set_type="time", work_seconds=60
    )

    assert result.workout.celebrations == []


async def test_log_set_tracks_weight_and_e1rm_independently(session: AsyncSession) -> None:
    """225x5 has a higher e1RM than 235x1 even though 235 is the heavier weight —
    the heavier-but-lower-rep set should only celebrate the weight PR, not e1RM."""
    await workouts.log_set(session, TEST_USER, exercise="Deadlift", reps=5, weight=225)

    result = await workouts.log_set(session, TEST_USER, exercise="Deadlift", reps=1, weight=235)

    kinds = {c.kind for c in result.workout.celebrations}
    assert kinds == {"weight"}


async def test_log_set_reports_the_previous_value_on_a_later_pr(session: AsyncSession) -> None:
    await workouts.log_set(session, TEST_USER, exercise="Deadlift", reps=5, weight=225)

    result = await workouts.log_set(session, TEST_USER, exercise="Deadlift", reps=5, weight=245)

    weight_celebration = next(c for c in result.workout.celebrations if c.kind == "weight")
    assert weight_celebration.value == 245
    assert weight_celebration.previous == 225


async def test_get_streak_target_from_planned_workouts_count(session: AsyncSession) -> None:
    template = await templates.create_workout_template(
        session, TEST_USER, name="Legs", exercises=[{"exercise": "Squat", "sets": 3, "reps": 5}]
    )
    today = date.today()
    await planned_service.plan_workout(
        session, TEST_USER, template_id=template.id, scheduled_for=today
    )
    await planned_service.plan_workout(
        session, TEST_USER, template_id=template.id, scheduled_for=today + timedelta(days=1)
    )

    streak = await service.get_streak(session, TEST_USER, as_of=today)

    assert streak.target == 2


async def test_get_streak_falls_back_to_3_with_no_planned_workouts(session: AsyncSession) -> None:
    streak = await service.get_streak(session, TEST_USER, as_of=date.today())

    assert streak.target == 3


async def test_get_streak_this_week_counts_any_workout_type(session: AsyncSession) -> None:
    today = date.today()
    await workouts.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "Squat", "sets": [{"weight": 100, "reps": 5}]}],
        logged_at=_at(today),
    )
    await workouts.log_activity(
        session, TEST_USER, activity_type="yoga", duration_minutes=30, logged_at=_at(today)
    )

    streak = await service.get_streak(session, TEST_USER, as_of=today)

    assert streak.this_week == 2


async def test_get_streak_current_week_counts_as_a_bonus_once_target_is_met(
    session: AsyncSession,
) -> None:
    today = date.today()
    monday = _monday(today)
    for i in range(3):
        await workouts.log_activity(
            session,
            TEST_USER,
            activity_type="yoga",
            duration_minutes=30,
            logged_at=_at(monday + timedelta(days=i)),
        )

    streak = await service.get_streak(session, TEST_USER, as_of=monday)

    assert streak.this_week == 3
    assert streak.target == 3
    assert streak.weeks == 1


async def test_get_streak_backward_walk_stops_at_a_shortfall(session: AsyncSession) -> None:
    today = date.today()
    monday = _monday(today)
    # This week: hits the fallback target of 3.
    for i in range(3):
        await workouts.log_activity(
            session,
            TEST_USER,
            activity_type="yoga",
            duration_minutes=30,
            logged_at=_at(monday + timedelta(days=i)),
        )
    # Last week: falls short (only 1 of 3).
    last_monday = monday - timedelta(days=7)
    await workouts.log_activity(
        session, TEST_USER, activity_type="yoga", duration_minutes=30, logged_at=_at(last_monday)
    )
    # Two weeks ago: would otherwise meet target, but the streak should have
    # already stopped at last week's shortfall.
    two_ago_monday = monday - timedelta(days=14)
    for i in range(3):
        await workouts.log_activity(
            session,
            TEST_USER,
            activity_type="yoga",
            duration_minutes=30,
            logged_at=_at(two_ago_monday + timedelta(days=i)),
        )

    streak = await service.get_streak(session, TEST_USER, as_of=monday)

    assert streak.weeks == 1


async def test_get_streak_multi_week_run(session: AsyncSession) -> None:
    today = date.today()
    monday = _monday(today)
    for weeks_back in range(3):
        week_monday = monday - timedelta(days=7 * weeks_back)
        for i in range(3):
            await workouts.log_activity(
                session,
                TEST_USER,
                activity_type="yoga",
                duration_minutes=30,
                logged_at=_at(week_monday + timedelta(days=i)),
            )

    streak = await service.get_streak(session, TEST_USER, as_of=monday)

    assert streak.weeks == 3


async def test_get_streak_is_scoped_to_owner(session: AsyncSession) -> None:
    today = date.today()
    monday = _monday(today)
    for i in range(3):
        await workouts.log_activity(
            session,
            OTHER_USER,
            activity_type="yoga",
            duration_minutes=30,
            logged_at=_at(monday + timedelta(days=i)),
        )

    streak = await service.get_streak(session, TEST_USER, as_of=monday)

    assert streak.this_week == 0


async def test_finish_workout_attaches_streak(session: AsyncSession) -> None:
    started = await workouts.start_workout(session, TEST_USER, exercises=["Deadlift"])

    finished = await workouts.finish_workout(session, TEST_USER, workout_id=started.id)

    assert finished is not None
    assert finished.streak is not None
    assert finished.streak.this_week >= 1


async def test_recompute_pr_updates_weight_and_e1rm_independently(session: AsyncSession) -> None:
    workout = await workouts.log_workout(
        session,
        TEST_USER,
        exercises=[
            {
                "exercise": "Overhead Press",
                "sets": [{"weight": 100, "reps": 10}, {"weight": 120, "reps": 1}],
            }
        ],
    )
    exercise_id = workout.exercises[0].exercise_id
    set_b = next(s for s in workout.exercises[0].sets if float(s.weight) == 120)

    # 120x1 holds the weight record; 100x10 (e1rm 133.3) holds the e1RM record —
    # set independently at creation time.
    assert await _pr_value(session, TEST_USER, exercise_id, PersonalRecordKind.weight) == 120
    assert await _pr_value(session, TEST_USER, exercise_id, PersonalRecordKind.e1rm) == Decimal(
        "133.3"
    )

    # Editing set B's reps up (120x1 -> 120x5, e1rm 140.0) should only move the
    # e1RM record to it — the weight record was already correct and unaffected.
    result = await session.execute(select(WorkoutSet).where(WorkoutSet.id == set_b.id))
    orm_set = result.scalar_one()
    orm_set.actual_reps = 5
    await session.flush()

    await service.recompute_pr(
        session, TEST_USER, exercise_id=exercise_id, kind=PersonalRecordKind.weight
    )
    await service.recompute_pr(
        session, TEST_USER, exercise_id=exercise_id, kind=PersonalRecordKind.e1rm
    )

    assert await _pr_value(session, TEST_USER, exercise_id, PersonalRecordKind.weight) == 120
    assert await _pr_value(session, TEST_USER, exercise_id, PersonalRecordKind.e1rm) == Decimal(
        "140.0"
    )


async def test_recompute_pr_does_not_touch_an_unrelated_exercise(session: AsyncSession) -> None:
    ohp = await workouts.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "Overhead Press", "sets": [{"weight": 95, "reps": 5}]}],
    )
    squat = await workouts.log_workout(
        session, TEST_USER, exercises=[{"exercise": "Squat", "sets": [{"weight": 225, "reps": 5}]}]
    )
    ohp_exercise_id = ohp.exercises[0].exercise_id
    squat_exercise_id = squat.exercises[0].exercise_id

    await service.recompute_pr(
        session, TEST_USER, exercise_id=ohp_exercise_id, kind=PersonalRecordKind.weight
    )

    assert await _pr_value(session, TEST_USER, squat_exercise_id, PersonalRecordKind.weight) == 225


async def test_log_set_over_rest_includes_celebrations(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/workouts/log-set", json={"exercise": "Deadlift", "reps": 5, "weight": "225"}
    )

    assert resp.status_code == 200
    kinds = {c["kind"] for c in resp.json()["workout"]["celebrations"]}
    assert kinds == {"weight", "e1rm"}


async def test_finish_workout_over_rest_includes_streak(client: AsyncClient) -> None:
    start_resp = await client.post("/api/workouts/start", json={"exercises": ["Deadlift"]})
    workout_id = start_resp.json()["id"]

    resp = await client.post(f"/api/workouts/{workout_id}/finish", json={})

    assert resp.status_code == 200
    assert resp.json()["streak"]["this_week"] >= 1
