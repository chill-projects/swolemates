from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workouts import WeeklyPatternDay
from app.services import planned_workouts as service
from app.services import workout_templates as templates
from app.services import workouts
from app.services.timezones import today_in
from tests.conftest import OTHER_USER, TEST_USER

# `get_today_planned` resolves "today" in a timezone; pin one so the tests don't depend
# on where the machine running them happens to be relative to UTC's date boundary.
TZ = ZoneInfo("America/Los_Angeles")


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
        session, TEST_USER, template_id=legs.id, scheduled_for=today_in(TZ)
    )

    today_planned = await service.get_today_planned(session, TEST_USER, tz=TZ)

    assert today_planned is not None
    assert today_planned.id == planned.id
    assert today_planned.template_name == "Legs"


async def test_get_today_planned_ignores_a_future_entry(session: AsyncSession) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    await service.plan_workout(
        session, TEST_USER, template_id=legs.id, scheduled_for=today_in(TZ) + timedelta(days=1)
    )

    assert await service.get_today_planned(session, TEST_USER, tz=TZ) is None


async def test_get_today_planned_is_none_once_skipped(session: AsyncSession) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    planned = await service.plan_workout(
        session, TEST_USER, template_id=legs.id, scheduled_for=today_in(TZ)
    )
    await service.update_planned_workout(session, TEST_USER, planned_id=planned.id, action="skip")

    assert await service.get_today_planned(session, TEST_USER, tz=TZ) is None


async def test_get_today_planned_is_scoped_to_the_caller(session: AsyncSession) -> None:
    legs = await _make_template(session, OTHER_USER, "Legs")
    await service.plan_workout(session, OTHER_USER, template_id=legs.id, scheduled_for=today_in(TZ))

    assert await service.get_today_planned(session, TEST_USER, tz=TZ) is None


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


async def test_set_weekly_pattern_resyncs_an_untouched_materialized_date(
    session: AsyncSession,
) -> None:
    """The typo'd-then-fixed case: Monday got materialized as Legs, then the
    pattern is corrected to Pool before anyone's touched that Monday. The Plan
    page's own copy promises "change a day and the next seven days follow" —
    this is that promise, for a day that was already generated when the fix
    landed."""
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

    # Same rows resynced in place — not deleted and regenerated, which would
    # shrink or grow the week's streak target.
    assert {p.id for p in first} == {p.id for p in second}
    assert all(p.template_name == "Pool" for p in second if p.scheduled_for.weekday() == 0)


async def test_get_planned_workouts_resyncs_a_row_that_went_stale_earlier(
    session: AsyncSession,
) -> None:
    """Self-healing on read. A row can be stale without set_weekly_pattern ever
    having had the chance to fix it — it was materialized under an older deploy, or
    the pattern was corrected before the write-side resync existed. Reading the plan
    brings it back in line rather than leaving it wrong until the pattern is edited
    again."""
    legs = await _make_template(session, TEST_USER, "Legs")
    pool = await _make_template(session, TEST_USER, "Pool")
    today = date.today()
    # Materialize today under the wrong template, bypassing set_weekly_pattern
    # entirely, then point the pattern at the right one.
    planned = await service.plan_workout(
        session, TEST_USER, template_id=pool.id, scheduled_for=today
    )
    await session.execute(
        WeeklyPatternDay.__table__.insert().values(
            user_id=TEST_USER, day_of_week=today.weekday(), template_id=legs.id
        )
    )

    refreshed = await service.get_planned_workouts(session, TEST_USER, start=today, end=today)

    assert [p.id for p in refreshed] == [planned.id]  # same row, not a replacement
    assert refreshed[0].template_name == "Legs"


async def test_get_planned_workouts_leaves_a_started_row_alone_when_resyncing(
    session: AsyncSession,
) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    pool = await _make_template(session, TEST_USER, "Pool")
    today = date.today()
    planned = await service.plan_workout(
        session, TEST_USER, template_id=pool.id, scheduled_for=today
    )
    await workouts.start_workout(session, TEST_USER, planned_id=planned.id)
    await session.execute(
        WeeklyPatternDay.__table__.insert().values(
            user_id=TEST_USER, day_of_week=today.weekday(), template_id=legs.id
        )
    )

    refreshed = await service.get_planned_workouts(session, TEST_USER, start=today, end=today)

    assert refreshed[0].template_name == "Pool"


async def test_set_weekly_pattern_does_not_resync_a_past_date(session: AsyncSession) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    pool = await _make_template(session, TEST_USER, "Pool")
    yesterday = date.today() - timedelta(days=1)
    planned = await service.plan_workout(
        session, TEST_USER, template_id=legs.id, scheduled_for=yesterday
    )

    await service.set_weekly_pattern(
        session, TEST_USER, days=[{"day_of_week": yesterday.weekday(), "template_id": pool.id}]
    )

    refetched = await service.get_planned_workout(session, TEST_USER, planned.id)
    assert refetched.template_name == "Legs"


async def test_set_weekly_pattern_does_not_resync_a_skipped_entry(session: AsyncSession) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    pool = await _make_template(session, TEST_USER, "Pool")
    today = date.today()
    planned = await service.plan_workout(
        session, TEST_USER, template_id=legs.id, scheduled_for=today
    )
    await service.update_planned_workout(session, TEST_USER, planned_id=planned.id, action="skip")

    await service.set_weekly_pattern(
        session, TEST_USER, days=[{"day_of_week": today.weekday(), "template_id": pool.id}]
    )

    refetched = await service.get_planned_workout(session, TEST_USER, planned.id)
    assert refetched.template_name == "Legs"


async def test_set_weekly_pattern_does_not_resync_a_started_entry(session: AsyncSession) -> None:
    legs = await _make_template(session, TEST_USER, "Legs")
    pool = await _make_template(session, TEST_USER, "Pool")
    today = date.today()
    planned = await service.plan_workout(
        session, TEST_USER, template_id=legs.id, scheduled_for=today
    )
    await workouts.start_workout(session, TEST_USER, planned_id=planned.id)

    await service.set_weekly_pattern(
        session, TEST_USER, days=[{"day_of_week": today.weekday(), "template_id": pool.id}]
    )

    refetched = await service.get_planned_workout(session, TEST_USER, planned.id)
    assert refetched.template_name == "Legs"


async def test_set_weekly_pattern_leaves_an_untouched_date_when_the_day_becomes_rest(
    session: AsyncSession,
) -> None:
    """Deliberately conservative: turning a day to rest doesn't delete its
    already-materialized, still-untouched entry — deleting would shrink the
    week's streak target the same way an explicit skip is barred from doing.
    It's left visible, one Skip away from matching the new pattern."""
    legs = await _make_template(session, TEST_USER, "Legs")
    today = date.today()
    planned = await service.plan_workout(
        session, TEST_USER, template_id=legs.id, scheduled_for=today
    )

    await service.set_weekly_pattern(session, TEST_USER, days=[])

    refetched = await service.get_planned_workout(session, TEST_USER, planned.id)
    assert refetched.template_name == "Legs"


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
