"""The weekly check-in.

Every number here is composed from a service that has its own tests, so these don't
re-test streaks or calendars — they test the assembly: that the two windows are the
right seven days, that the review reads without writing, and that the decisions fire on
states a user can actually reach.

`as_of` is pinned in every test. The whole point of the module is a Sunday-night
ritual, so "what day is it" is load-bearing, and a suite that inherits it from the
clock is one that passes on Tuesday and fails on Sunday.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workouts import PlannedWorkout
from app.services import planned_workouts
from app.services import weekly_checkin as service
from app.services import workout_templates as templates
from app.services import workouts as workouts_service
from tests.conftest import TEST_USER

TZ = ZoneInfo("UTC")
# A Sunday — the day the check-in is designed around.
SUNDAY = date(2026, 9, 13)


async def _template(session: AsyncSession, name: str) -> templates.TemplateOut:
    return await templates.create_workout_template(
        session, TEST_USER, name=name, exercises=[{"exercise": "Squat", "sets": 3, "reps": 5}]
    )


async def _log_on(session: AsyncSession, day: date, exercise: str = "Squat") -> None:
    await workouts_service.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": exercise, "sets": [{"weight": 225, "reps": 5}]}],
        logged_at=datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=12),
    )


async def test_review_covers_the_seven_days_ending_on_as_of(session: AsyncSession) -> None:
    """Inclusive of `as_of`, exclusive of the day before the window. A Sunday check-in
    has to count the session done that morning."""
    await _log_on(session, SUNDAY)  # today
    await _log_on(session, SUNDAY - timedelta(days=6))  # first day in window
    await _log_on(session, SUNDAY - timedelta(days=7))  # one day too early

    checkin = await service.get_weekly_checkin(session, TEST_USER, as_of=SUNDAY, tz=TZ)

    assert checkin.review.start == SUNDAY - timedelta(days=6)
    assert checkin.review.end == SUNDAY
    assert checkin.review.sessions_completed == 2


async def test_upcoming_covers_the_seven_days_after_as_of(session: AsyncSession) -> None:
    """On a Sunday that's Monday through the following Sunday — the week being planned,
    never the one that just ended."""
    legs = await _template(session, "Legs")
    await planned_workouts.set_weekly_pattern(
        session, TEST_USER, days=[{"day_of_week": 0, "template_id": legs.id}]
    )

    checkin = await service.get_weekly_checkin(session, TEST_USER, as_of=SUNDAY, tz=TZ)

    assert [s.scheduled_for for s in checkin.upcoming] == [SUNDAY + timedelta(days=1)]
    assert checkin.upcoming[0].template_name == "Legs"


async def test_sessions_planned_comes_from_the_pattern_and_writes_nothing(
    session: AsyncSession,
) -> None:
    """The count of what was planned must not be read by generating planned rows for the
    past — `get_planned_workouts` materializes any range it's asked about, so a review
    that used it would quietly backfill a history of sessions nobody ever scheduled."""
    legs = await _template(session, "Legs")
    await planned_workouts.set_weekly_pattern(
        session,
        TEST_USER,
        days=[
            {"day_of_week": 0, "template_id": legs.id},
            {"day_of_week": 2, "template_id": legs.id},
            {"day_of_week": 4, "template_id": legs.id},
        ],
    )

    checkin = await service.get_weekly_checkin(session, TEST_USER, as_of=SUNDAY, tz=TZ)

    assert checkin.review.sessions_planned == 3
    rows = await session.execute(
        select(PlannedWorkout.scheduled_for).where(
            PlannedWorkout.user_id == TEST_USER, PlannedWorkout.scheduled_for <= SUNDAY
        )
    )
    assert list(rows.scalars()) == [], "the review generated planned rows in the past"


async def test_carried_notes_surface_the_most_recent_note_per_exercise(
    session: AsyncSession,
) -> None:
    """One per exercise: a note is guidance for the next time you do the movement, so an
    older one for the same lift has already been superseded."""
    await workouts_service.log_workout(
        session,
        TEST_USER,
        exercises=[
            {
                "exercise": "Barbell Bench Press",
                "sets": [{"weight": 185, "reps": 5}],
                "next_time_note": "felt heavy, hold the weight",
            }
        ],
        logged_at=datetime(2026, 9, 9, 12, tzinfo=UTC),
    )
    await workouts_service.log_workout(
        session,
        TEST_USER,
        exercises=[
            {
                "exercise": "Barbell Bench Press",
                "sets": [{"weight": 185, "reps": 6}],
                "next_time_note": "better — try 190",
            }
        ],
        logged_at=datetime(2026, 9, 11, 12, tzinfo=UTC),
    )

    checkin = await service.get_weekly_checkin(session, TEST_USER, as_of=SUNDAY, tz=TZ)

    assert [n.note for n in checkin.carried_notes] == ["better — try 190"]
    assert checkin.carried_notes[0].logged_on == date(2026, 9, 11)


async def test_carried_notes_ignore_sessions_outside_the_window(session: AsyncSession) -> None:
    await workouts_service.log_workout(
        session,
        TEST_USER,
        exercises=[
            {
                "exercise": "Deadlift",
                "sets": [{"weight": 315, "reps": 3}],
                "next_time_note": "from a fortnight ago",
            }
        ],
        logged_at=datetime(2026, 8, 30, 12, tzinfo=UTC),
    )

    checkin = await service.get_weekly_checkin(session, TEST_USER, as_of=SUNDAY, tz=TZ)

    assert checkin.carried_notes == []


async def test_no_pattern_is_the_only_decision_when_nothing_is_set(
    session: AsyncSession,
) -> None:
    checkin = await service.get_weekly_checkin(session, TEST_USER, as_of=SUNDAY, tz=TZ)

    assert [d.kind for d in checkin.decisions] == ["no_pattern"]


async def test_an_archived_template_on_a_patterned_day_is_surfaced(
    session: AsyncSession,
) -> None:
    """The silent failure this exists to catch: `_generate_missing` treats an archived
    template as a rest day, so the day just stops appearing with nothing to explain it."""
    legs = await _template(session, "Legs")
    await planned_workouts.set_weekly_pattern(
        session, TEST_USER, days=[{"day_of_week": 0, "template_id": legs.id}]
    )
    await templates.archive_workout_template(session, TEST_USER, legs.id)

    checkin = await service.get_weekly_checkin(session, TEST_USER, as_of=SUNDAY, tz=TZ)

    kinds = [d.kind for d in checkin.decisions]
    assert "archived_template" in kinds
    assert "Monday" in next(d.detail for d in checkin.decisions if d.kind == "archived_template")
    assert checkin.upcoming == [], "an archived template schedules nothing"


async def test_a_healthy_week_raises_no_decisions(session: AsyncSession) -> None:
    legs = await _template(session, "Legs")
    await planned_workouts.set_weekly_pattern(
        session, TEST_USER, days=[{"day_of_week": 0, "template_id": legs.id}]
    )

    checkin = await service.get_weekly_checkin(session, TEST_USER, as_of=SUNDAY, tz=TZ)

    assert checkin.decisions == []


async def test_summary_stands_alone(session: AsyncSession) -> None:
    """It's the text a non-UI MCP host shows and the body a notification would carry, so
    it has to carry the numbers without the structured payload beside it."""
    legs = await _template(session, "Legs")
    await planned_workouts.set_weekly_pattern(
        session, TEST_USER, days=[{"day_of_week": 0, "template_id": legs.id}]
    )
    await _log_on(session, SUNDAY - timedelta(days=2))

    checkin = await service.get_weekly_checkin(session, TEST_USER, as_of=SUNDAY, tz=TZ)

    assert "1 of 1 sessions" in checkin.summary
    assert "Legs (Mon)" in checkin.summary


async def test_windows_are_bucketed_in_the_callers_zone(session: AsyncSession) -> None:
    """A 9pm-Pacific session on the last day of the window is already the next day in
    UTC. It belongs to the week the user lived, not the one the server did."""
    la = ZoneInfo("America/Los_Angeles")
    await workouts_service.log_workout(
        session,
        TEST_USER,
        exercises=[{"exercise": "Squat", "sets": [{"weight": 225, "reps": 5}]}],
        logged_at=datetime(2026, 9, 14, 4, 0, tzinfo=UTC),  # 2026-09-13 21:00 PDT
    )

    in_la = await service.get_weekly_checkin(session, TEST_USER, as_of=SUNDAY, tz=la)
    in_utc = await service.get_weekly_checkin(session, TEST_USER, as_of=SUNDAY, tz=TZ)

    assert in_la.review.sessions_completed == 1
    assert in_utc.review.sessions_completed == 0


async def test_get_weekly_checkin_over_rest(client: AsyncClient) -> None:
    resp = await client.get("/api/weekly-checkin", params={"as_of": SUNDAY.isoformat()})

    assert resp.status_code == 200
    body = resp.json()
    assert body["as_of"] == SUNDAY.isoformat()
    assert body["review"]["start"] == (SUNDAY - timedelta(days=6)).isoformat()
    assert body["summary"]
