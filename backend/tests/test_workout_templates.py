import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import workout_templates as service
from app.services import workouts
from tests.conftest import OTHER_USER, TEST_USER


async def test_create_workout_template(session: AsyncSession) -> None:
    template = await service.create_workout_template(
        session,
        TEST_USER,
        name="Pull Day",
        exercises=[
            {"exercise": "Deadlift", "sets": 3, "reps": 5, "weight": 225},
            {"exercise": "Plank", "sets": 3, "seconds": 60},
        ],
    )

    assert template.name == "Pull Day"
    assert len(template.exercises) == 2
    deadlift = template.exercises[0]
    assert deadlift.sets == 3
    assert deadlift.reps == 5
    assert float(deadlift.weight) == 225
    assert deadlift.superset_group is None


async def test_create_workout_template_custom_exercise_accepts_a_chosen_muscle_group(
    session: AsyncSession,
) -> None:
    template = await service.create_workout_template(
        session,
        TEST_USER,
        name="Leg Day",
        exercises=[
            {"exercise": "Cable Hip Abduction", "sets": 3, "reps": 15, "muscle_group": "legs"},
        ],
    )

    exercises = await workouts.list_exercises(session, TEST_USER)
    custom = next(e for e in exercises if e.name == "Cable Hip Abduction")
    assert custom.muscle_group == "legs"
    assert template.exercises[0].exercise_name == "Cable Hip Abduction"


async def test_create_workout_template_rejects_an_unknown_muscle_group(
    session: AsyncSession,
) -> None:
    with pytest.raises(ValueError, match="muscle_group must be one of"):
        await service.create_workout_template(
            session,
            TEST_USER,
            name="Leg Day",
            exercises=[
                {
                    "exercise": "Cable Hip Abduction",
                    "sets": 3,
                    "reps": 15,
                    "muscle_group": "glutes",
                },
            ],
        )


async def test_create_workout_template_groups_supersets(session: AsyncSession) -> None:
    template = await service.create_workout_template(
        session,
        TEST_USER,
        name="Push Day",
        exercises=[
            {"exercise": "Bench Press", "sets": 3, "reps": 8, "group": 1},
            {"exercise": "Overhead Press", "sets": 3, "reps": 8, "group": 1},
        ],
    )

    groups = {e.superset_group for e in template.exercises}
    assert groups == {1}


@pytest.mark.parametrize(
    ("exercises", "match"),
    [
        ([], "at least one exercise"),
        ([{"exercise": "Squat", "sets": 0, "reps": 5}], "sets > 0"),
        ([{"exercise": "Squat", "sets": 3, "reps": 5, "seconds": 30}], "exactly one of"),
        ([{"exercise": "Squat", "sets": 3}], "exactly one of"),
    ],
)
async def test_create_workout_template_validation(
    session: AsyncSession, exercises: list[dict], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        await service.create_workout_template(session, TEST_USER, name="Bad", exercises=exercises)


async def test_get_workout_template_404s_for_another_users_template(
    session: AsyncSession,
) -> None:
    template = await service.create_workout_template(
        session, TEST_USER, name="Legs", exercises=[{"exercise": "Squat", "sets": 3, "reps": 5}]
    )

    with pytest.raises(service.NotFoundError):
        await service.get_workout_template(session, OTHER_USER, template.id)


async def test_list_workout_templates_excludes_archived(session: AsyncSession) -> None:
    keep = await service.create_workout_template(
        session, TEST_USER, name="Keep", exercises=[{"exercise": "Squat", "sets": 3, "reps": 5}]
    )
    archived = await service.create_workout_template(
        session, TEST_USER, name="Archived", exercises=[{"exercise": "Squat", "sets": 3, "reps": 5}]
    )
    await service.archive_workout_template(session, TEST_USER, archived.id)

    listed = await service.list_workout_templates(session, TEST_USER)

    assert {t.id for t in listed} == {keep.id}


async def test_update_workout_template_rename(session: AsyncSession) -> None:
    template = await service.create_workout_template(
        session, TEST_USER, name="Old Name", exercises=[{"exercise": "Squat", "sets": 3, "reps": 5}]
    )

    updated = await service.update_workout_template(
        session, TEST_USER, template_id=template.id, action="rename", name="New Name"
    )

    assert updated.name == "New Name"


async def test_update_workout_template_add_exercise_as_superset(session: AsyncSession) -> None:
    template = await service.create_workout_template(
        session, TEST_USER, name="Legs", exercises=[{"exercise": "Squat", "sets": 3, "reps": 5}]
    )
    squat_te = template.exercises[0].id

    updated = await service.update_workout_template(
        session,
        TEST_USER,
        template_id=template.id,
        action="add_exercise",
        exercise="Lunge",
        sets=3,
        reps=10,
        superset_with=squat_te,
    )

    groups = {e.superset_group for e in updated.exercises}
    assert len(groups) == 1
    assert None not in groups


async def test_update_workout_template_remove_exercise(session: AsyncSession) -> None:
    template = await service.create_workout_template(
        session,
        TEST_USER,
        name="Legs",
        exercises=[
            {"exercise": "Squat", "sets": 3, "reps": 5},
            {"exercise": "Lunge", "sets": 3, "reps": 10},
        ],
    )
    to_remove = template.exercises[1].id

    updated = await service.update_workout_template(
        session,
        TEST_USER,
        template_id=template.id,
        action="remove_exercise",
        template_exercise_id=to_remove,
    )

    assert [e.exercise_name for e in updated.exercises] == ["Squat"]


async def test_update_workout_template_reorder(session: AsyncSession) -> None:
    template = await service.create_workout_template(
        session,
        TEST_USER,
        name="Legs",
        exercises=[
            {"exercise": "Squat", "sets": 3, "reps": 5},
            {"exercise": "Lunge", "sets": 3, "reps": 10},
        ],
    )
    ids = [e.id for e in template.exercises]

    updated = await service.update_workout_template(
        session,
        TEST_USER,
        template_id=template.id,
        action="reorder_exercises",
        order=list(reversed(ids)),
    )

    assert [e.id for e in updated.exercises] == list(reversed(ids))


async def test_update_workout_template_reorder_rejects_mismatched_list(
    session: AsyncSession,
) -> None:
    template = await service.create_workout_template(
        session, TEST_USER, name="Legs", exercises=[{"exercise": "Squat", "sets": 3, "reps": 5}]
    )

    with pytest.raises(ValueError, match="current exercises"):
        await service.update_workout_template(
            session,
            TEST_USER,
            template_id=template.id,
            action="reorder_exercises",
            order=[template.exercises[0].id, uuid.uuid4()],
        )


async def test_update_workout_template_update_exercise_is_a_partial_patch(
    session: AsyncSession,
) -> None:
    template = await service.create_workout_template(
        session,
        TEST_USER,
        name="Legs",
        exercises=[{"exercise": "Squat", "sets": 3, "reps": 5, "weight": 135, "notes": "go deep"}],
    )
    te_id = template.exercises[0].id

    updated = await service.update_workout_template(
        session,
        TEST_USER,
        template_id=template.id,
        action="update_exercise",
        template_exercise_id=te_id,
        weight=145,
    )

    entry = updated.exercises[0]
    assert float(entry.weight) == 145
    assert entry.reps == 5
    assert entry.notes == "go deep"


async def test_update_workout_template_rejects_an_archived_template(
    session: AsyncSession,
) -> None:
    template = await service.create_workout_template(
        session, TEST_USER, name="Legs", exercises=[{"exercise": "Squat", "sets": 3, "reps": 5}]
    )
    await service.archive_workout_template(session, TEST_USER, template.id)

    with pytest.raises(ValueError, match="archived"):
        await service.update_workout_template(
            session, TEST_USER, template_id=template.id, action="rename", name="Nope"
        )


async def test_update_workout_template_404s_for_another_users_template(
    session: AsyncSession,
) -> None:
    template = await service.create_workout_template(
        session, TEST_USER, name="Legs", exercises=[{"exercise": "Squat", "sets": 3, "reps": 5}]
    )

    with pytest.raises(service.NotFoundError):
        await service.update_workout_template(
            session, OTHER_USER, template_id=template.id, action="rename", name="Mine now"
        )


async def test_archive_workout_template_404s_for_another_users_template(
    session: AsyncSession,
) -> None:
    template = await service.create_workout_template(
        session, TEST_USER, name="Legs", exercises=[{"exercise": "Squat", "sets": 3, "reps": 5}]
    )

    with pytest.raises(service.NotFoundError):
        await service.archive_workout_template(session, OTHER_USER, template.id)


async def test_start_workout_from_template_copies_prescription_and_supersets(
    session: AsyncSession,
) -> None:
    template = await service.create_workout_template(
        session,
        TEST_USER,
        name="Push Day",
        exercises=[
            {"exercise": "Bench Press", "sets": 4, "reps": 6, "weight": 185, "group": 1},
            {"exercise": "Overhead Press", "sets": 3, "reps": 8, "weight": 95, "group": 1},
            {"exercise": "Plank", "sets": 3, "seconds": 45},
        ],
    )

    workout = await workouts.start_workout(session, TEST_USER, template_id=template.id)

    names = [e.exercise_name for e in workout.exercises]
    assert names == ["Bench Press", "Overhead Press", "Plank"]
    bench, ohp, plank = workout.exercises
    assert bench.superset_group == ohp.superset_group
    assert bench.superset_group is not None
    assert plank.superset_group is None
    assert bench.target.sets == 4
    assert bench.target.reps == 6
    assert float(bench.target.weight) == 185
    assert plank.target.seconds == 45
    assert plank.target.reps is None
    assert bench.sets == []


async def test_start_workout_from_template_404s_for_another_users_template(
    session: AsyncSession,
) -> None:
    template = await service.create_workout_template(
        session, TEST_USER, name="Legs", exercises=[{"exercise": "Squat", "sets": 3, "reps": 5}]
    )

    with pytest.raises(service.NotFoundError):
        await workouts.start_workout(session, OTHER_USER, template_id=template.id)


async def test_create_workout_template_over_rest(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/templates",
        json={
            "name": "Pull Day",
            "exercises": [{"exercise": "Deadlift", "sets": 3, "reps": 5, "weight": "225"}],
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Pull Day"
    assert body["exercises"][0]["exercise_name"] == "Deadlift"


async def test_create_workout_template_over_rest_400s_on_invalid_exercise(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/api/templates", json={"name": "Bad", "exercises": [{"exercise": "Squat", "sets": 0}]}
    )

    assert resp.status_code == 400


async def test_list_workout_templates_over_rest(client: AsyncClient) -> None:
    await client.post(
        "/api/templates",
        json={"name": "Legs", "exercises": [{"exercise": "Squat", "sets": 3, "reps": 5}]},
    )

    resp = await client.get("/api/templates")

    assert resp.status_code == 200
    assert any(t["name"] == "Legs" for t in resp.json())


async def test_get_workout_template_over_rest(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/templates",
        json={"name": "Legs", "exercises": [{"exercise": "Squat", "sets": 3, "reps": 5}]},
    )
    template_id = create_resp.json()["id"]

    resp = await client.get(f"/api/templates/{template_id}")

    assert resp.status_code == 200
    assert resp.json()["name"] == "Legs"


async def test_update_workout_template_over_rest(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/templates",
        json={"name": "Legs", "exercises": [{"exercise": "Squat", "sets": 3, "reps": 5}]},
    )
    template_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/templates/{template_id}/entries", json={"action": "rename", "name": "Legs v2"}
    )

    assert resp.status_code == 200
    assert resp.json()["name"] == "Legs v2"


async def test_archive_workout_template_over_rest(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/templates",
        json={"name": "Legs", "exercises": [{"exercise": "Squat", "sets": 3, "reps": 5}]},
    )
    template_id = create_resp.json()["id"]

    resp = await client.post(f"/api/templates/{template_id}/archive")

    assert resp.status_code == 200
    listed = await client.get("/api/templates")
    assert not any(t["id"] == template_id for t in listed.json())


async def test_start_workout_with_template_id_over_rest(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/templates",
        json={
            "name": "Push Day",
            "exercises": [{"exercise": "Bench Press", "sets": 4, "reps": 6, "weight": "185"}],
        },
    )
    template_id = create_resp.json()["id"]

    resp = await client.post("/api/workouts/start", json={"template_id": template_id})

    assert resp.status_code == 201
    body = resp.json()
    assert body["exercises"][0]["exercise_name"] == "Bench Press"
    assert body["exercises"][0]["target"]["sets"] == 4
