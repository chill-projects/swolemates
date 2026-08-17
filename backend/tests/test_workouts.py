from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workouts import Workout, WorkoutExercise, WorkoutSet
from app.services import workouts as service
from tests.conftest import OTHER_USER, TEST_USER


async def _backdate_last_activity(session: AsyncSession, workout_id, when: datetime) -> None:
    result = await session.execute(
        select(WorkoutSet)
        .join(WorkoutExercise, WorkoutSet.workout_exercise_id == WorkoutExercise.id)
        .where(WorkoutExercise.workout_id == workout_id)
    )
    for s in result.scalars():
        s.completed_at = when
    await session.flush()


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


async def test_start_workout_creates_a_new_one(session: AsyncSession) -> None:
    workout = await service.start_workout(session, TEST_USER)

    assert workout.resumed is False
    assert workout.completed_at is None
    assert workout.exercises == []


async def test_start_workout_resumes_an_existing_active_one(session: AsyncSession) -> None:
    first = await service.start_workout(session, TEST_USER, exercises=["Deadlift"])
    second = await service.start_workout(session, TEST_USER, exercises=["Bench Press"])

    assert second.id == first.id
    assert second.resumed is True
    assert [e.exercise_name for e in second.exercises] == ["Deadlift"]


async def test_start_workout_pre_populates_named_exercises(session: AsyncSession) -> None:
    workout = await service.start_workout(session, TEST_USER, exercises=["Deadlift", "Bench Press"])

    names = [e.exercise_name for e in workout.exercises]
    assert names == ["Deadlift", "Bench Press"]
    assert all(e.sets == [] for e in workout.exercises)


async def test_log_set_auto_starts_when_nothing_active(session: AsyncSession) -> None:
    result = await service.log_set(session, TEST_USER, exercise="Back Squat", reps=5, weight=185)

    assert result.needs_clarification is None
    entry = result.workout.exercises[0]
    assert entry.exercise_name == "Back Squat"
    assert len(entry.sets) == 1
    assert entry.sets[0].reps == 5


async def test_log_set_auto_continues_within_the_window(session: AsyncSession) -> None:
    first = await service.log_set(session, TEST_USER, exercise="Back Squat", reps=5, weight=185)
    second = await service.log_set(session, TEST_USER, exercise="Back Squat", reps=5, weight=190)

    assert second.workout.id == first.workout.id
    assert len(second.workout.exercises[0].sets) == 2


async def test_log_set_sets_repeat_count_creates_multiple_rows(session: AsyncSession) -> None:
    result = await service.log_set(
        session, TEST_USER, exercise="Back Squat", reps=5, weight=185, sets=3
    )

    entry = result.workout.exercises[0]
    assert len(entry.sets) == 3
    assert [s.set_number for s in entry.sets] == [1, 2, 3]


async def test_log_set_returns_clarification_past_the_window_without_writing(
    session: AsyncSession,
) -> None:
    first = await service.log_set(session, TEST_USER, exercise="Back Squat", reps=5, weight=185)
    await _backdate_last_activity(session, first.workout.id, datetime.now(UTC) - timedelta(hours=3))

    result = await service.log_set(session, TEST_USER, exercise="Back Squat", reps=5, weight=190)

    assert result.workout is None
    assert result.needs_clarification is not None
    assert "3.0h ago" in result.needs_clarification

    active = await service.get_active_workout(session, TEST_USER)
    assert active.id == first.workout.id
    assert len(active.exercises[0].sets) == 1


async def test_log_set_continue_session_true_continues_the_stale_workout(
    session: AsyncSession,
) -> None:
    first = await service.log_set(session, TEST_USER, exercise="Back Squat", reps=5, weight=185)
    await _backdate_last_activity(session, first.workout.id, datetime.now(UTC) - timedelta(hours=3))

    result = await service.log_set(
        session, TEST_USER, exercise="Back Squat", reps=5, weight=190, continue_session=True
    )

    assert result.workout.id == first.workout.id
    assert len(result.workout.exercises[0].sets) == 2


async def test_log_set_continue_session_false_finishes_stale_and_starts_fresh(
    session: AsyncSession,
) -> None:
    first = await service.log_set(session, TEST_USER, exercise="Back Squat", reps=5, weight=185)
    await _backdate_last_activity(session, first.workout.id, datetime.now(UTC) - timedelta(hours=3))

    result = await service.log_set(
        session, TEST_USER, exercise="Back Squat", reps=5, weight=190, continue_session=False
    )

    assert result.workout.id != first.workout.id
    assert len(result.workout.exercises[0].sets) == 1

    stale = await session.get(Workout, first.workout.id)
    assert stale.completed_at is not None
    assert stale.completed_at < datetime.now(UTC) - timedelta(hours=1)


async def test_log_set_is_scoped_to_owner(session: AsyncSession) -> None:
    mine = await service.log_set(session, TEST_USER, exercise="Back Squat", reps=5, weight=185)
    theirs = await service.log_set(session, OTHER_USER, exercise="Back Squat", reps=5, weight=225)

    assert mine.workout.id != theirs.workout.id
    active = await service.get_active_workout(session, TEST_USER)
    assert active.id == mine.workout.id


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"reps": 0, "weight": 0}, "reps > 0"),
        ({"reps": 5, "weight": -1}, "needs a weight"),
        ({"set_type": "time", "work_seconds": 0}, "work seconds > 0"),
    ],
)
async def test_log_set_validation_ported_from_legacy(
    session: AsyncSession, kwargs: dict, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        await service.log_set(session, TEST_USER, exercise="Push-up", **kwargs)


async def test_finish_workout_stamps_completed_at_and_drops_unlogged_sets(
    session: AsyncSession,
) -> None:
    started = await service.start_workout(session, TEST_USER, exercises=["Deadlift"])
    workout_exercise = (
        await session.execute(
            select(WorkoutExercise).where(WorkoutExercise.workout_id == started.id)
        )
    ).scalar_one()
    session.add(
        WorkoutSet(workout_exercise_id=workout_exercise.id, set_number=1, completed_at=None)
    )
    await session.flush()

    finished = await service.finish_workout(session, TEST_USER, workout_id=started.id)

    assert finished.completed_at is not None
    assert finished.exercises[0].sets == []


async def test_finish_workout_404s_for_another_users_workout(session: AsyncSession) -> None:
    workout = await service.start_workout(session, TEST_USER)

    with pytest.raises(service.NotFoundError):
        await service.finish_workout(session, OTHER_USER, workout_id=workout.id)


async def test_finish_workout_allows_zero_logged_sets(session: AsyncSession) -> None:
    workout = await service.start_workout(session, TEST_USER)

    finished = await service.finish_workout(
        session, TEST_USER, workout_id=workout.id, notes="short one"
    )

    assert finished.completed_at is not None
    assert finished.notes == "short one"


async def test_get_active_workout_returns_none_when_nothing_active(session: AsyncSession) -> None:
    assert await service.get_active_workout(session, TEST_USER) is None


async def test_get_active_workout_returns_the_in_progress_one(session: AsyncSession) -> None:
    started = await service.start_workout(session, TEST_USER, exercises=["Deadlift"])

    active = await service.get_active_workout(session, TEST_USER)

    assert active.id == started.id


async def test_get_workout_live_groups_solo_exercises_separately(session: AsyncSession) -> None:
    workout = await service.start_workout(session, TEST_USER, exercises=["Deadlift", "Bench Press"])

    live = await service.get_workout_live(session, TEST_USER, workout)

    assert len(live.groups) == 2
    assert all(not g.is_superset and g.superset_group is None for g in live.groups)
    assert [g.exercises[0].exercise_name for g in live.groups] == ["Deadlift", "Bench Press"]


async def test_update_workout_entry_add_exercise_as_superset_groups_them(
    session: AsyncSession,
) -> None:
    workout = await service.start_workout(session, TEST_USER, exercises=["Deadlift"])
    deadlift_id = workout.exercises[0].id

    workout = await service.update_workout_entry(
        session,
        TEST_USER,
        workout_id=workout.id,
        action="add_exercise",
        exercise="Overhead Press",
        superset_with=deadlift_id,
    )
    live = await service.get_workout_live(session, TEST_USER, workout)

    assert len(live.groups) == 1
    group = live.groups[0]
    assert group.is_superset is True
    assert group.superset_group is not None
    assert {e.exercise_name for e in group.exercises} == {"Deadlift", "Overhead Press"}


async def test_update_workout_entry_add_exercise_solo_by_default(session: AsyncSession) -> None:
    workout = await service.start_workout(session, TEST_USER)

    workout = await service.update_workout_entry(
        session, TEST_USER, workout_id=workout.id, action="add_exercise", exercise="Deadlift"
    )

    assert len(workout.exercises) == 1
    assert workout.exercises[0].superset_group is None


async def test_update_workout_entry_remove_exercise_requires_zero_sets(
    session: AsyncSession,
) -> None:
    result = await service.log_set(session, TEST_USER, exercise="Back Squat", reps=5, weight=185)
    we_id = result.workout.exercises[0].id

    with pytest.raises(ValueError, match="already has logged sets"):
        await service.update_workout_entry(
            session,
            TEST_USER,
            workout_id=result.workout.id,
            action="remove_exercise",
            workout_exercise_id=we_id,
        )


async def test_update_workout_entry_remove_exercise_succeeds_with_no_sets(
    session: AsyncSession,
) -> None:
    workout = await service.start_workout(session, TEST_USER, exercises=["Deadlift", "Squat"])
    to_remove = workout.exercises[1].id

    workout = await service.update_workout_entry(
        session,
        TEST_USER,
        workout_id=workout.id,
        action="remove_exercise",
        workout_exercise_id=to_remove,
    )

    assert [e.exercise_name for e in workout.exercises] == ["Deadlift"]


async def test_update_workout_entry_reorder_exercises(session: AsyncSession) -> None:
    workout = await service.start_workout(session, TEST_USER, exercises=["Deadlift", "Squat"])
    ids = [e.id for e in workout.exercises]

    workout = await service.update_workout_entry(
        session,
        TEST_USER,
        workout_id=workout.id,
        action="reorder_exercises",
        order=list(reversed(ids)),
    )

    assert [e.id for e in workout.exercises] == list(reversed(ids))


async def test_update_workout_entry_reorder_rejects_mismatched_list(session: AsyncSession) -> None:
    workout = await service.start_workout(session, TEST_USER, exercises=["Deadlift", "Squat"])
    bogus_id = workout.exercises[0].id

    with pytest.raises(ValueError, match="current exercises"):
        await service.update_workout_entry(
            session, TEST_USER, workout_id=workout.id, action="reorder_exercises", order=[bogus_id]
        )


async def test_update_workout_entry_set_next_time_note(session: AsyncSession) -> None:
    workout = await service.start_workout(session, TEST_USER, exercises=["Deadlift"])
    we_id = workout.exercises[0].id

    workout = await service.update_workout_entry(
        session,
        TEST_USER,
        workout_id=workout.id,
        action="set_next_time_note",
        workout_exercise_id=we_id,
        note="add 5 next time",
    )

    assert workout.exercises[0].next_time_note == "add 5 next time"


async def test_update_workout_entry_rejects_unknown_action(session: AsyncSession) -> None:
    workout = await service.start_workout(session, TEST_USER)

    with pytest.raises(ValueError, match="Unknown action"):
        await service.update_workout_entry(
            session, TEST_USER, workout_id=workout.id, action="bogus"
        )


async def test_update_workout_entry_404s_for_another_users_workout(session: AsyncSession) -> None:
    workout = await service.start_workout(session, TEST_USER)

    with pytest.raises(service.NotFoundError):
        await service.update_workout_entry(
            session, OTHER_USER, workout_id=workout.id, action="add_exercise", exercise="Deadlift"
        )


async def test_update_workout_entry_rejects_a_finished_workout(session: AsyncSession) -> None:
    workout = await service.start_workout(session, TEST_USER)
    finished = await service.finish_workout(session, TEST_USER, workout_id=workout.id)

    with pytest.raises(ValueError, match="already finished"):
        await service.update_workout_entry(
            session,
            TEST_USER,
            workout_id=finished.id,
            action="add_exercise",
            exercise="Deadlift",
        )


async def test_get_workout_live_last_time_from_most_recent_finished_workout(
    session: AsyncSession,
) -> None:
    old = await service.log_set(session, TEST_USER, exercise="Back Squat", reps=5, weight=135)
    await service.finish_workout(session, TEST_USER, workout_id=old.workout.id)

    recent = await service.log_set(session, TEST_USER, exercise="Back Squat", reps=8, weight=145)
    await service.finish_workout(session, TEST_USER, workout_id=recent.workout.id)

    current = await service.start_workout(session, TEST_USER, exercises=["Back Squat"])
    live = await service.get_workout_live(session, TEST_USER, current)

    entry = live.groups[0].exercises[0]
    assert entry.last_time is not None
    assert entry.last_time.sets[0].weight == 145
    assert entry.last_time.sets[0].reps == 8


async def test_get_workout_live_last_time_excludes_the_current_workout(
    session: AsyncSession,
) -> None:
    workout = await service.start_workout(session, TEST_USER, exercises=["Back Squat"])
    live = await service.get_workout_live(session, TEST_USER, workout)

    assert live.groups[0].exercises[0].last_time is None


async def test_get_workout_live_last_time_none_when_never_done_before(
    session: AsyncSession,
) -> None:
    workout = await service.start_workout(session, TEST_USER, exercises=["Deadlift"])

    live = await service.get_workout_live(session, TEST_USER, workout)

    assert live.groups[0].exercises[0].last_time is None


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


async def test_start_workout_over_rest(client: AsyncClient) -> None:
    resp = await client.post("/api/workouts/start", json={"exercises": ["Deadlift"]})

    assert resp.status_code == 201
    body = resp.json()
    assert body["resumed"] is False
    assert body["exercises"][0]["exercise_name"] == "Deadlift"


async def test_log_set_over_rest(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/workouts/log-set", json={"exercise": "Back Squat", "reps": 5, "weight": "185"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["needs_clarification"] is None
    assert body["workout"]["exercises"][0]["exercise_name"] == "Back Squat"


async def test_finish_workout_over_rest(client: AsyncClient) -> None:
    start_resp = await client.post("/api/workouts/start", json={})
    workout_id = start_resp.json()["id"]

    resp = await client.post(f"/api/workouts/{workout_id}/finish", json={})

    assert resp.status_code == 200
    assert resp.json()["completed_at"] is not None


async def test_get_active_workout_over_rest_returns_null_when_none(client: AsyncClient) -> None:
    resp = await client.get("/api/workouts/active")

    assert resp.status_code == 200
    assert resp.json() is None


async def test_get_workout_live_over_rest(client: AsyncClient) -> None:
    start_resp = await client.post("/api/workouts/start", json={"exercises": ["Deadlift"]})
    workout_id = start_resp.json()["id"]

    resp = await client.get(f"/api/workouts/{workout_id}/live")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["groups"]) == 1
    assert body["groups"][0]["exercises"][0]["exercise_name"] == "Deadlift"


async def test_update_workout_entry_over_rest(client: AsyncClient) -> None:
    start_resp = await client.post("/api/workouts/start", json={"exercises": ["Deadlift"]})
    workout_id = start_resp.json()["id"]

    resp = await client.post(
        f"/api/workouts/{workout_id}/entries",
        json={"action": "add_exercise", "exercise": "Bench Press"},
    )

    assert resp.status_code == 200
    names = {e["exercise_name"] for g in resp.json()["groups"] for e in g["exercises"]}
    assert names == {"Deadlift", "Bench Press"}


async def test_update_workout_entry_over_rest_400s_on_bad_action(client: AsyncClient) -> None:
    start_resp = await client.post("/api/workouts/start", json={})
    workout_id = start_resp.json()["id"]

    resp = await client.post(
        f"/api/workouts/{workout_id}/entries", json={"action": "not_a_real_action"}
    )

    assert resp.status_code == 400


async def test_list_workout_exercises_over_rest(client: AsyncClient) -> None:
    resp = await client.get("/api/workouts/exercises")

    assert resp.status_code == 200
    names = {e["name"] for e in resp.json()}
    assert "Deadlift" in names
