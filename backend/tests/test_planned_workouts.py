from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import planned_workouts as service
from app.services import workout_templates as templates
from app.services import workouts
from tests.conftest import OTHER_USER, TEST_USER


async def _make_template(session: AsyncSession, user: str, name: str) -> templates.TemplateOut:
    return await templates.create_workout_template(
        session, user, name=name, exercises=[{"exercise": "Squat", "sets": 3, "reps": 5}]
    )


async def test_set_weekly_pattern_replaces_the_whole_week(session: AsyncSession) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    pool = await _make_template(session, TEST_USER, "Pool")

    await service.set_weekly_pattern(
        session, TEST_USER, days=[{"day_of_week": 0, "template_id": legs.id}]
    )
    pattern = await service.set_weekly_pattern(
        session, TEST_USER, days=[{"day_of_week": 1, "template_id": pool.id}]
    )

    assert [d.day_of_week for d in pattern] == [1]
    assert pattern[0].template_name == "Pool"


@pytest.mark.parametrize(
    ("days", "match"),
    [
        ([{"day_of_week": 7, "template_id": None}], "0-6"),
        ([{"day_of_week": -1, "template_id": None}], "0-6"),
        (
            [{"day_of_week": 0, "template_id": None}, {"day_of_week": 0, "template_id": None}],
            "more than once",
        ),
    ],
)
async def test_set_weekly_pattern_validation(
    session: AsyncSession, days: list[dict], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        await service.set_weekly_pattern(session, TEST_USER, days=days)


async def test_set_weekly_pattern_rejects_an_archived_template(session: AsyncSession) -> None:
    template = await _make_template(session, TEST_USER, "Legs")
    await templates.archive_workout_template(session, TEST_USER, template.id)

    with pytest.raises(ValueError, match="archived"):
        await service.set_weekly_pattern(
            session, TEST_USER, days=[{"day_of_week": 0, "template_id": template.id}]
        )


async def test_set_weekly_pattern_404s_for_another_users_template(session: AsyncSession) -> None:
    template = await _make_template(session, OTHER_USER, "Legs")

    with pytest.raises(service.NotFoundError):
        await service.set_weekly_pattern(
            session, TEST_USER, days=[{"day_of_week": 0, "template_id": template.id}]
        )


async def test_get_planned_workouts_generates_from_the_pattern(session: AsyncSession) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    pool = await _make_template(session, TEST_USER, "Pool")
    await service.set_weekly_pattern(
        session,
        TEST_USER,
        days=[
            {"day_of_week": 0, "template_id": legs.id},
            {"day_of_week": 1, "template_id": pool.id},
        ],
    )

    start = date.today()
    end = start + timedelta(days=13)
    planned = await service.get_planned_workouts(session, TEST_USER, start=start, end=end)

    mondays = [p for p in planned if p.scheduled_for.weekday() == 0]
    tuesdays = [p for p in planned if p.scheduled_for.weekday() == 1]
    others = [p for p in planned if p.scheduled_for.weekday() not in (0, 1)]
    assert len(mondays) == 2
    assert len(tuesdays) == 2
    assert others == []
    assert all(p.template_name == "Legs" for p in mondays)
    assert all(p.exercise_names == ["Squat"] for p in mondays)


async def test_get_planned_workouts_is_idempotent(session: AsyncSession) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    await service.set_weekly_pattern(
        session, TEST_USER, days=[{"day_of_week": 0, "template_id": legs.id}]
    )
    start = date.today()
    end = start + timedelta(days=13)

    first = await service.get_planned_workouts(session, TEST_USER, start=start, end=end)
    second = await service.get_planned_workouts(session, TEST_USER, start=start, end=end)

    assert len(first) == len(second)
    assert {p.id for p in first} == {p.id for p in second}


async def test_get_today_planned_is_none_with_nothing_scheduled(session: AsyncSession) -> None:
    assert await service.get_today_planned(session, TEST_USER) is None


async def test_get_today_planned_returns_todays_unstarted_entry(session: AsyncSession) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    planned = await service.plan_workout(
        session, TEST_USER, template_id=legs.id, scheduled_for=date.today()
    )

    today_planned = await service.get_today_planned(session, TEST_USER)

    assert today_planned is not None
    assert today_planned.id == planned.id
    assert today_planned.template_name == "Legs"


async def test_get_today_planned_ignores_a_future_entry(session: AsyncSession) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    await service.plan_workout(
        session, TEST_USER, template_id=legs.id, scheduled_for=date.today() + timedelta(days=1)
    )

    assert await service.get_today_planned(session, TEST_USER) is None


async def test_get_today_planned_is_none_once_skipped(session: AsyncSession) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    planned = await service.plan_workout(
        session, TEST_USER, template_id=legs.id, scheduled_for=date.today()
    )
    await service.update_planned_workout(session, TEST_USER, planned_id=planned.id, action="skip")

    assert await service.get_today_planned(session, TEST_USER) is None


async def test_get_today_planned_is_scoped_to_the_caller(session: AsyncSession) -> None:
    legs = await _make_template(session, OTHER_USER, "Legs")
    await service.plan_workout(
        session, OTHER_USER, template_id=legs.id, scheduled_for=date.today()
    )

    assert await service.get_today_planned(session, TEST_USER) is None


async def test_get_planned_workouts_skips_rest_days(session: AsyncSession) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    await service.set_weekly_pattern(
        session, TEST_USER, days=[{"day_of_week": 0, "template_id": legs.id}]
    )
    start = date.today()
    end = start + timedelta(days=6)

    planned = await service.get_planned_workouts(session, TEST_USER, start=start, end=end)

    non_mondays = [p for p in planned if p.scheduled_for.weekday() != 0]
    assert non_mondays == []


async def test_get_planned_workouts_skips_archived_templates(session: AsyncSession) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    await service.set_weekly_pattern(
        session, TEST_USER, days=[{"day_of_week": 0, "template_id": legs.id}]
    )
    await templates.archive_workout_template(session, TEST_USER, legs.id)

    start = date.today()
    end = start + timedelta(days=6)
    planned = await service.get_planned_workouts(session, TEST_USER, start=start, end=end)

    assert planned == []


async def test_get_planned_workouts_does_not_retroactively_change_materialized_dates(
    session: AsyncSession,
) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    pool = await _make_template(session, TEST_USER, "Pool")
    await service.set_weekly_pattern(
        session, TEST_USER, days=[{"day_of_week": 0, "template_id": legs.id}]
    )
    start = date.today()
    end = start + timedelta(days=6)
    first = await service.get_planned_workouts(session, TEST_USER, start=start, end=end)

    await service.set_weekly_pattern(
        session, TEST_USER, days=[{"day_of_week": 0, "template_id": pool.id}]
    )
    second = await service.get_planned_workouts(session, TEST_USER, start=start, end=end)

    assert {p.id for p in first} == {p.id for p in second}
    assert all(p.template_name == "Legs" for p in second if p.scheduled_for.weekday() == 0)


async def test_plan_workout_allows_a_second_entry_on_the_same_day(session: AsyncSession) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    pool = await _make_template(session, TEST_USER, "Pool")
    when = date.today()

    first = await service.plan_workout(session, TEST_USER, template_id=legs.id, scheduled_for=when)
    second = await service.plan_workout(session, TEST_USER, template_id=pool.id, scheduled_for=when)

    assert first.id != second.id
    planned = await service.get_planned_workouts(session, TEST_USER, start=when, end=when)
    assert len(planned) == 2


async def test_plan_workout_rejects_an_archived_template(session: AsyncSession) -> None:
    template = await _make_template(session, TEST_USER, "Legs")
    await templates.archive_workout_template(session, TEST_USER, template.id)

    with pytest.raises(ValueError, match="archived"):
        await service.plan_workout(
            session, TEST_USER, template_id=template.id, scheduled_for=date.today()
        )


async def test_update_planned_workout_skip_and_unskip(session: AsyncSession) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    planned = await service.plan_workout(
        session, TEST_USER, template_id=legs.id, scheduled_for=date.today()
    )

    skipped = await service.update_planned_workout(
        session, TEST_USER, planned_id=planned.id, action="skip"
    )
    assert skipped.status.value == "skipped"

    unskipped = await service.update_planned_workout(
        session, TEST_USER, planned_id=planned.id, action="unskip"
    )
    assert unskipped.status.value == "planned"


async def test_update_planned_workout_rejects_unskip_when_not_skipped(
    session: AsyncSession,
) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    planned = await service.plan_workout(
        session, TEST_USER, template_id=legs.id, scheduled_for=date.today()
    )

    with pytest.raises(ValueError, match="skipped"):
        await service.update_planned_workout(
            session, TEST_USER, planned_id=planned.id, action="unskip"
        )


async def test_update_planned_workout_rejects_skip_once_started(session: AsyncSession) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    planned = await service.plan_workout(
        session, TEST_USER, template_id=legs.id, scheduled_for=date.today()
    )
    await workouts.start_workout(session, TEST_USER, planned_id=planned.id)

    with pytest.raises(ValueError, match="not-yet-started"):
        await service.update_planned_workout(
            session, TEST_USER, planned_id=planned.id, action="skip"
        )


async def test_update_planned_workout_404s_for_another_users_entry(session: AsyncSession) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    planned = await service.plan_workout(
        session, TEST_USER, template_id=legs.id, scheduled_for=date.today()
    )

    with pytest.raises(service.NotFoundError):
        await service.update_planned_workout(
            session, OTHER_USER, planned_id=planned.id, action="skip"
        )


async def test_start_workout_from_planned_links_and_finish_marks_done(
    session: AsyncSession,
) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    planned = await service.plan_workout(
        session, TEST_USER, template_id=legs.id, scheduled_for=date.today()
    )

    workout = await workouts.start_workout(session, TEST_USER, planned_id=planned.id)
    assert workout.exercises[0].exercise_name == "Squat"

    mid = await service.get_planned_workout(session, TEST_USER, planned.id)
    assert mid.workout_id == workout.id
    assert mid.status.value == "planned"

    await workouts.finish_workout(session, TEST_USER, workout_id=workout.id)

    done = await service.get_planned_workout(session, TEST_USER, planned.id)
    assert done.status.value == "done"
    assert done.workout_id == workout.id


async def test_start_workout_from_planned_404s_for_another_users_entry(
    session: AsyncSession,
) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    planned = await service.plan_workout(
        session, TEST_USER, template_id=legs.id, scheduled_for=date.today()
    )

    with pytest.raises(service.NotFoundError):
        await workouts.start_workout(session, OTHER_USER, planned_id=planned.id)


async def test_set_weekly_pattern_over_rest(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/templates",
        json={"name": "Legs", "exercises": [{"exercise": "Squat", "sets": 3, "reps": 5}]},
    )
    template_id = create_resp.json()["id"]

    resp = await client.put(
        "/api/weekly-pattern", json={"days": [{"day_of_week": 0, "template_id": template_id}]}
    )

    assert resp.status_code == 200
    assert resp.json() == [{"day_of_week": 0, "template_id": template_id, "template_name": "Legs"}]


async def test_get_planned_workouts_over_rest(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/templates",
        json={"name": "Legs", "exercises": [{"exercise": "Squat", "sets": 3, "reps": 5}]},
    )
    template_id = create_resp.json()["id"]
    await client.put(
        "/api/weekly-pattern", json={"days": [{"day_of_week": 0, "template_id": template_id}]}
    )

    resp = await client.get("/api/planned-workouts")

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_plan_workout_over_rest(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/templates",
        json={"name": "Legs", "exercises": [{"exercise": "Squat", "sets": 3, "reps": 5}]},
    )
    template_id = create_resp.json()["id"]

    resp = await client.post(
        "/api/planned-workouts",
        json={"template_id": template_id, "scheduled_for": date.today().isoformat()},
    )

    assert resp.status_code == 201
    assert resp.json()["template_name"] == "Legs"


async def test_update_planned_workout_over_rest(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/templates",
        json={"name": "Legs", "exercises": [{"exercise": "Squat", "sets": 3, "reps": 5}]},
    )
    template_id = create_resp.json()["id"]
    plan_resp = await client.post(
        "/api/planned-workouts",
        json={"template_id": template_id, "scheduled_for": date.today().isoformat()},
    )
    planned_id = plan_resp.json()["id"]

    resp = await client.post(f"/api/planned-workouts/{planned_id}/entries", json={"action": "skip"})

    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"


async def test_start_workout_with_planned_id_over_rest(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/templates",
        json={"name": "Legs", "exercises": [{"exercise": "Squat", "sets": 3, "reps": 5}]},
    )
    template_id = create_resp.json()["id"]
    plan_resp = await client.post(
        "/api/planned-workouts",
        json={"template_id": template_id, "scheduled_for": date.today().isoformat()},
    )
    planned_id = plan_resp.json()["id"]

    resp = await client.post("/api/workouts/start", json={"planned_id": planned_id})

    assert resp.status_code == 201
    assert resp.json()["exercises"][0]["exercise_name"] == "Squat"
