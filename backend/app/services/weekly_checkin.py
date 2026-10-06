"""The weekly check-in — look back at the week that's ending, look ahead at the one
starting, and surface what needs deciding before it does.

Built for the Sunday-night ritual, but deliberately well-defined on any day: the two
windows are the seven days *ending* on `as_of` and the seven *starting* the day after.
Each therefore contains exactly one of every weekday, which is what makes "3 of the 4
sessions your pattern asks for" a fair comparison no matter when it's asked. Anchoring
to calendar weeks instead would make a Wednesday call compare four elapsed days against
a full week's target and report a shortfall that hasn't happened yet.

This module composes; it owns no queries of its own beyond the decisions. Everything it
reports already existed — the week's plan, the streaks, the notes people leave
themselves — scattered across five services and four screens. The check-in's whole
contribution is assembling it at the one moment it changes what you do next.

One function, both front doors: `get_weekly_checkin` backs the MCP tool and the Plan
page's card, and is the payload a scheduled notification would carry if one is built
later (see the notification design discussion). Nothing here knows about delivery.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workouts import PlannedWorkoutStatus
from app.services import celebrations, planned_workouts, workout_templates
from app.services import nutrition as nutrition_service
from app.services import profile as profile_service
from app.services import workouts as workouts_service
from app.services.celebrations import StreakOut
from app.services.timezones import today_in

WINDOW_DAYS = 7

# Enough to prompt without becoming a reading list. A week of training rarely leaves
# more than a handful of notes worth acting on, and a long tail of stale ones is how a
# check-in stops being read.
MAX_CARRIED_NOTES = 5

DecisionKind = Literal["no_pattern", "archived_template", "unplanned_week"]


@dataclass
class CheckinDecision:
    """Something that will quietly not happen unless the user acts before the week
    starts. Deliberately not "advice" — every one of these is a concrete state of their
    own data, not a suggestion about training."""

    kind: DecisionKind
    detail: str


@dataclass
class CarriedNote:
    """A `next_time_note` from the week just gone. These are the most preparation-shaped
    thing the schema holds — the user wrote them *for* this moment — and until now
    nothing resurfaced them at it; they were visible only inside the session that
    recorded them."""

    exercise_name: str
    note: str
    logged_on: date


@dataclass
class WeeklyReview:
    start: date
    end: date
    sessions_completed: int
    # From the weekly pattern, not from generated rows: reading the plan for a past
    # range would materialize planned entries retroactively (see
    # `planned_workouts._generate_missing`), and a review must not write.
    sessions_planned: int
    nutrition_days_logged: int


@dataclass
class UpcomingSession:
    scheduled_for: date
    template_name: str
    status: PlannedWorkoutStatus


@dataclass
class WeeklyCheckin:
    as_of: date
    review: WeeklyReview
    upcoming: list[UpcomingSession]
    carried_notes: list[CarriedNote] = field(default_factory=list)
    decisions: list[CheckinDecision] = field(default_factory=list)
    streak: StreakOut | None = None
    nutrition_streak: int = 0
    summary: str = ""


async def _decisions(
    session: AsyncSession,
    user_sub: str,
    *,
    pattern: list[planned_workouts.WeeklyPatternDayOut],
    upcoming: list[UpcomingSession],
) -> list[CheckinDecision]:
    """Only states that are certainly wrong, never opinions about training.

    A suggestion the user disagrees with teaches them to skim the whole check-in; a
    fact about their own configuration doesn't. "Your Wednesday points at a template
    you archived" is checkable and actionable. "You should squat more" is neither.
    """
    scheduled = [d for d in pattern if d.template_id is not None]
    if not scheduled:
        return [
            CheckinDecision(
                kind="no_pattern",
                detail="No weekly pattern set yet, so nothing gets scheduled. "
                "Pick which days you train and the plan fills itself in.",
            )
        ]

    decisions: list[CheckinDecision] = []

    # An archived template on a patterned day is a silent rest day: `_generate_missing`
    # treats it as "nothing to schedule" rather than failing, which is right at write
    # time and invisible at read time. This is the one place it becomes visible.
    templates: dict[uuid.UUID, workout_templates.TemplateOut] = {}
    for day in scheduled:
        assert day.template_id is not None  # narrowed by `scheduled`
        template = templates.get(day.template_id)
        if template is None:
            template = await workout_templates.get_workout_template(
                session, user_sub, day.template_id
            )
            templates[day.template_id] = template
        if template.archived_at is not None:
            decisions.append(
                CheckinDecision(
                    kind="archived_template",
                    detail=f"{_weekday_name(day.day_of_week)} is set to "
                    f"{template.name!r}, which is archived — nothing will be "
                    "scheduled that day until you point it somewhere else.",
                )
            )

    # The pattern says one thing and the week ahead says another. Reachable when every
    # patterned template is archived, or when the days were skipped ahead of time.
    if scheduled and not upcoming:
        decisions.append(
            CheckinDecision(
                kind="unplanned_week",
                detail="Nothing is on the calendar for the coming week even though "
                "your pattern has training days in it.",
            )
        )
    return decisions


def _weekday_name(day_of_week: int) -> str:
    return ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")[
        day_of_week
    ]


def _summary(checkin: WeeklyCheckin) -> str:
    """One line that has to stand alone — it's the text a non-UI MCP host shows, and the
    body a push notification would carry. Written so that reading only this is enough to
    decide whether to open anything."""
    review = checkin.review
    parts = [
        f"Last week: {review.sessions_completed} of {review.sessions_planned} sessions"
        if review.sessions_planned
        else f"Last week: {review.sessions_completed} sessions",
        f"{review.nutrition_days_logged}/{WINDOW_DAYS} days logged",
    ]
    if checkin.upcoming:
        names = ", ".join(
            f"{s.template_name} ({_weekday_name(s.scheduled_for.weekday())[:3]})"
            for s in checkin.upcoming
        )
        parts.append(f"ahead: {names}")
    else:
        parts.append("nothing scheduled yet for the week ahead")
    if checkin.carried_notes:
        count = len(checkin.carried_notes)
        parts.append(f"{count} note{'s' if count != 1 else ''} to pick up")
    if checkin.decisions:
        count = len(checkin.decisions)
        parts.append(f"{count} thing{'s' if count != 1 else ''} to sort out")
    return ". ".join(parts) + "."


async def get_weekly_checkin(
    session: AsyncSession,
    user_sub: str,
    *,
    as_of: date | None = None,
    tz: ZoneInfo | None = None,
) -> WeeklyCheckin:
    """Assemble the check-in. `as_of` is the day being stood on — "today" in the
    caller's zone by default — with the review covering the seven days ending on it and
    the plan the seven starting after it."""
    tz = tz or await profile_service.get_user_timezone(session, user_sub)
    as_of = as_of or today_in(tz)

    review_start = as_of - timedelta(days=WINDOW_DAYS - 1)
    ahead_start = as_of + timedelta(days=1)
    ahead_end = as_of + timedelta(days=WINDOW_DAYS)

    frequency = await celebrations.get_workout_frequency(session, user_sub, as_of=as_of, tz=tz)
    pattern = await planned_workouts.get_weekly_pattern(session, user_sub)
    calendar = await nutrition_service.get_nutrition_calendar(
        session, user_sub, start=review_start, end=as_of, tz=tz
    )
    planned = await planned_workouts.get_planned_workouts(
        session, user_sub, start=ahead_start, end=ahead_end
    )
    notes = await workouts_service.list_next_time_notes(
        session, user_sub, start=review_start, end=as_of, tz=tz, limit=MAX_CARRIED_NOTES
    )

    upcoming = [
        UpcomingSession(
            scheduled_for=p.scheduled_for, template_name=p.template_name, status=p.status
        )
        for p in planned
        if p.status != PlannedWorkoutStatus.skipped
    ]

    checkin = WeeklyCheckin(
        as_of=as_of,
        review=WeeklyReview(
            start=review_start,
            end=as_of,
            sessions_completed=frequency.workouts_last_7_days,
            sessions_planned=sum(1 for d in pattern if d.template_id is not None),
            # "Logged", not "hit" — the same bar `get_nutrition_streak` uses, and the
            # honest one for a review: a day you tracked and went over is a day you
            # tracked, and counting it as a miss punishes the behaviour being built.
            nutrition_days_logged=sum(1 for day in calendar if day.status != "no-data"),
        ),
        upcoming=upcoming,
        carried_notes=[
            CarriedNote(exercise_name=n.exercise_name, note=n.note, logged_on=n.logged_on)
            for n in notes
        ],
        decisions=await _decisions(session, user_sub, pattern=pattern, upcoming=upcoming),
        streak=await celebrations.get_streak(session, user_sub, as_of=as_of, tz=tz),
        nutrition_streak=await nutrition_service.get_nutrition_streak(
            session, user_sub, as_of=as_of, tz=tz
        ),
    )
    checkin.summary = _summary(checkin)
    return checkin
