from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import workouts as service
from tests.conftest import OTHER_USER, TEST_USER


async def test_starter_exercises_are_seeded(session: AsyncSession) -> None:
    exercises = await service.list_exercises(session, TEST_USER)
    names = {e.name for e in exercises}

    assert "Barbell Back Squat" in names
    assert "Deadlift" in names
    assert len(names) == 41
    assert all(not e.is_custom for e in exercises)


async def test_log_workout_writes_exercises_and_sets(session: AsyncSession) -> None:
    workout = await service.log_workout(
        session,
        TEST_USER,
        exercises=[
            {
                "exercise": "Barbell Back Squat",
                "sets": [
                    {"weight": 185, "reps": 5},
                    {"weight": 135, "reps": 8, "is_warmup": True},
                ],
            },
        ],
        title="Leg day",
    )

    assert workout.title == "Leg day"
    assert len(workout.exercises) == 1
    entry = workout.exercises[0]
    assert entry.exercise_name == "Barbell Back Squat"
    assert len(entry.sets) == 2
    assert float(entry.sets[0].weight) == 185
    assert entry.sets[0].reps == 5
    assert entry.sets[1].is_warmup is True


async def test_log_workout_auto_creates_a_custom_exercise(session: AsyncSession) -> None:
    workout = await service.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "Some Made Up Cable Thing", "sets": [{"weight": 40, "reps": 12}]}],
    )

    entry = workout.exercises[0]
    assert entry.exercise_name == "Some Made Up Cable Thing"

    exercises = await service.list_exercises(session, TEST_USER)
    custom = next(e for e in exercises if e.name == "Some Made Up Cable Thing")
    assert custom.is_custom is True
    assert custom.created_by == TEST_USER
    assert custom.muscle_group == "other"


async def test_log_workout_matches_the_catalog_case_insensitively(session: AsyncSession) -> None:
    first = await service.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "barbell back squat", "sets": [{"weight": 185, "reps": 5}]}],
    )
    second = await service.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "BARBELL BACK SQUAT", "sets": [{"weight": 190, "reps": 5}]}],
    )

    assert first.exercises[0].exercise_id == second.exercises[0].exercise_id
    exercises = await service.list_exercises(session, TEST_USER)
    assert sum(1 for e in exercises if e.name == "Barbell Back Squat") == 1


@pytest.mark.parametrize(
    ("exercises", "match"),
    [
        ([], "at least one exercise"),
        ([{"exercise": "Push-up", "sets": []}], "needs at least one set"),
        ([{"exercise": "Push-up", "sets": [{"reps": 0, "weight": 0}]}], "reps > 0"),
        ([{"exercise": "Push-up", "sets": [{"reps": 5, "weight": -1}]}], "needs a weight"),
        (
            [{"exercise": "Plank", "sets": [{"set_type": "time", "work_seconds": 0}]}],
            "work seconds > 0",
        ),
    ],
)
async def test_log_workout_validation_ported_from_legacy(
    session: AsyncSession, exercises: list[dict], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        await service.log_workout(session, TEST_USER, exercises=exercises)


async def test_log_activity_writes_a_non_strength_workout(session: AsyncSession) -> None:
    workout = await service.log_activity(
        session, TEST_USER, activity_type="yoga", duration_minutes=45, title="Morning flow"
    )

    assert workout.activity_type == "yoga"
    assert workout.duration_minutes == 45
    assert workout.exercises == []


async def test_log_activity_rejects_non_positive_duration(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        await service.log_activity(session, TEST_USER, activity_type="yoga", duration_minutes=0)


async def test_get_workout_history_filters_by_date_range(session: AsyncSession) -> None:
    old = datetime(2026, 1, 1, tzinfo=UTC)
    recent = datetime(2026, 8, 12, tzinfo=UTC)
    await service.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "Deadlift", "sets": [{"weight": 300, "reps": 3}]}],
        logged_at=old,
    )
    await service.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "Deadlift", "sets": [{"weight": 310, "reps": 3}]}],
        logged_at=recent,
    )

    history = await service.get_workout_history(
        session, TEST_USER, start=datetime(2026, 6, 1, tzinfo=UTC).date()
    )

    assert len(history) == 1
    assert float(history[0].exercises[0].sets[0].weight) == 310


async def test_get_workout_history_filters_by_exercise_and_is_scoped_to_owner(
    session: AsyncSession,
) -> None:
    await service.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "Deadlift", "sets": [{"weight": 300, "reps": 3}]}],
    )
    await service.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "Barbell Bench Press", "sets": [{"weight": 185, "reps": 5}]}],
    )
    await service.log_workout(
        session,
        OTHER_USER,
        exercises=[{"exercise": "Deadlift", "sets": [{"weight": 999, "reps": 1}]}],
    )

    history = await service.get_workout_history(session, TEST_USER, exercise="deadlift")

    assert len(history) == 1
    assert history[0].exercises[0].exercise_name == "Deadlift"
    assert float(history[0].exercises[0].sets[0].weight) == 300


async def test_log_workout_over_rest(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/workouts/log",
        json={
            "exercises": [
                {
                    "exercise": "Barbell Back Squat",
                    "sets": [{"weight": "185", "reps": 5}],
                }
            ],
            "title": "Leg day",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Leg day"
    assert body["exercises"][0]["exercise_name"] == "Barbell Back Squat"


async def test_log_workout_over_rest_400s_on_invalid_set(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/workouts/log",
        json={"exercises": [{"exercise": "Push-up", "sets": [{"reps": 0, "weight": 0}]}]},
    )
    assert resp.status_code == 400


async def test_log_activity_over_rest(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/workouts/log-activity",
        json={"activity_type": "yoga", "duration_minutes": 45},
    )
    assert resp.status_code == 201
    assert resp.json()["activity_type"] == "yoga"


async def test_get_workout_history_over_rest(client: AsyncClient) -> None:
    await client.post(
        "/api/workouts/log",
        json={"exercises": [{"exercise": "Deadlift", "sets": [{"weight": "300", "reps": 3}]}]},
    )

    resp = await client.get("/api/workouts", params={"exercise": "deadlift"})

    assert resp.status_code == 200
    assert len(resp.json()) == 1
