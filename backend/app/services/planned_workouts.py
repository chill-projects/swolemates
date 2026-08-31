"""Weekly pattern + planned workouts service (#3, resolved — slice 3b).

One-directional dependency, same technique as `workout_templates.py`: this module
imports from `workout_templates.py` (to read template detail for the "what's next"
view) at load time. `workouts.py` imports from *this* module inside
`start_workout`/`finish_workout` at call time, to avoid a cycle — `workouts.py` →
`planned_workouts.py` → `workout_templates.py` → `workouts.py` would be a real one
if all three were module-level imports.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workouts import PlannedWorkout, PlannedWorkoutStatus, WeeklyPatternDay
from app.services import profile as profile_service
from app.services import workout_templates
from app.services.errors import NotFoundError
from app.services.timezones import today_in


@dataclass
class WeeklyPatternDayOut:
    day_of_week: int
    template_id: uuid.UUID | None
    template_name: str | None


@dataclass
class PlannedWorkoutOut:
    id: uuid.UUID
    template_id: uuid.UUID
    template_name: str
    scheduled_for: date
    status: PlannedWorkoutStatus
    workout_id: uuid.UUID | None
    note: str | None
    # Deliberately light — a plain name list, not full target/superset/last-time
    # detail. That's the template editor's and the live view's job; showing it
    # twice here would just invite drift.
    exercise_names: list[str] = field(default_factory=list)


def _to_planned_out(
    p: PlannedWorkout, template: workout_templates.TemplateOut
) -> PlannedWorkoutOut:
    return PlannedWorkoutOut(
        id=p.id,
        template_id=p.template_id,
        template_name=template.name,
        scheduled_for=p.scheduled_for,
        status=p.status,
        workout_id=p.workout_id,
        note=p.note,
        exercise_names=[e.exercise_name for e in template.exercises if e.exercise_name],
    )


async def _require_non_archived_template(
    session: AsyncSession, user_sub: str, template_id: uuid.UUID
) -> workout_templates.TemplateOut:
    template = await workout_templates.get_workout_template(session, user_sub, template_id)
    if template.archived_at is not None:
        raise ValueError(f"Template {template.name!r} is archived.")
    return template


async def _resync_untouched_planned(
    session: AsyncSession, user_sub: str, days: list[dict], today: date
) -> None:
    """A pattern edit reaches forward into what's already materialized, but only
    for a row nothing has happened to yet: still `status == planned`, never
    started (`workout_id IS NULL`), dated today or later. That's the "change a
    day and the next seven days follow" the Plan page's own copy promises — a
    typo'd day fixed before it's lived through should actually fix, not leave a
    stale template sitting there under the corrected pattern. A day already
    started, finished, or explicitly skipped is a real thing that happened and
    stays exactly as it was, same as a date in the past — `update_planned_
    workout`'s "skip" already leans on this: the row count behind the week's
    streak target can't shrink just because something got acted on, and rewriting
    an acted-on row's template out from under it is the same kind of retroactive
    surprise. A day newly set to rest is left alone rather than deleted, for the
    same reason — it's still visible, just easy to Skip.
    """
    new_template_by_dow = {
        entry["day_of_week"]: entry["template_id"]
        for entry in days
        if entry.get("template_id") is not None
    }
    if not new_template_by_dow:
        return

    result = await session.execute(
        select(PlannedWorkout).where(
            PlannedWorkout.user_id == user_sub,
            PlannedWorkout.status == PlannedWorkoutStatus.planned,
            PlannedWorkout.workout_id.is_(None),
            PlannedWorkout.scheduled_for >= today,
        )
    )
    for planned in result.scalars():
        new_template_id = new_template_by_dow.get(planned.scheduled_for.weekday())
        if new_template_id is not None and new_template_id != planned.template_id:
            planned.template_id = new_template_id


async def set_weekly_pattern(
    session: AsyncSession, user_sub: str, *, days: list[dict]
) -> list[WeeklyPatternDayOut]:
    """`days`: [{"day_of_week": 0-6, "template_id"?: uuid.UUID}] — one entry per
    day you want scheduled; omit a day (or pass `template_id=None`) for a rest day.
    Replaces the caller's entire pattern in one call. Shapes weeks `get_planned_
    workouts` generates after this call, and also resyncs any already-materialized
    but still-untouched row forward — see `_resync_untouched_planned`."""
    seen: set[int] = set()
    for entry in days:
        dow = entry.get("day_of_week")
        if dow is None or not (0 <= dow <= 6):
            raise ValueError("day_of_week must be 0-6.")
        if dow in seen:
            raise ValueError(f"day_of_week {dow} given more than once.")
        seen.add(dow)
        template_id = entry.get("template_id")
        if template_id is not None:
            await _require_non_archived_template(session, user_sub, template_id)

    await session.execute(delete(WeeklyPatternDay).where(WeeklyPatternDay.user_id == user_sub))
    for entry in days:
        session.add(
            WeeklyPatternDay(
                user_id=user_sub,
                day_of_week=entry["day_of_week"],
                template_id=entry.get("template_id"),
            )
        )
    await session.flush()

    tz = await profile_service.get_user_timezone(session, user_sub)
    await _resync_untouched_planned(session, user_sub, days, today_in(tz))
    await session.flush()

    return await get_weekly_pattern(session, user_sub)


async def get_weekly_pattern(session: AsyncSession, user_sub: str) -> list[WeeklyPatternDayOut]:
    result = await session.execute(
        select(WeeklyPatternDay).where(WeeklyPatternDay.user_id == user_sub)
    )
    days = list(result.scalars())
    templates: dict[uuid.UUID, workout_templates.TemplateOut] = {}
    out = []
    for d in days:
        name = None
        if d.template_id is not None:
            template = templates.get(d.template_id)
            if template is None:
                template = await workout_templates._load_template(session, d.template_id)
                templates[d.template_id] = template
            name = template.name
        out.append(
            WeeklyPatternDayOut(
                day_of_week=d.day_of_week, template_id=d.template_id, template_name=name
            )
        )
    return sorted(out, key=lambda d: d.day_of_week)


async def plan_workout(
    session: AsyncSession, user_sub: str, *, template_id: uuid.UUID, scheduled_for: date
) -> PlannedWorkoutOut:
    """Adds one planned session — doesn't check for an existing entry on the same
    date, so an extra session on an already-planned day is allowed on purpose."""
    template = await _require_non_archived_template(session, user_sub, template_id)
    planned = PlannedWorkout(
        user_id=user_sub,
        template_id=template_id,
        scheduled_for=scheduled_for,
        status=PlannedWorkoutStatus.planned,
    )
    session.add(planned)
    await session.flush()
    return _to_planned_out(planned, template)


async def _generate_missing(session: AsyncSession, user_sub: str, start: date, end: date) -> None:
    # Serializes concurrent calls for the same user within this transaction — without
    # it, two overlapping get_planned_workouts calls (e.g. the Planned page's initial
    # fetch racing its own SSE-triggered refetch) can each see a date as "missing"
    # before either commits, and both insert a duplicate planned entry. Released
    # automatically at transaction end; scoped by a fixed namespace key so it can't
    # collide with an unrelated advisory lock elsewhere.
    await session.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtext("planned_workouts_generate"), func.hashtext(user_sub)
            )
        )
    )

    pattern_result = await session.execute(
        select(WeeklyPatternDay).where(WeeklyPatternDay.user_id == user_sub)
    )
    pattern_by_dow = {p.day_of_week: p for p in pattern_result.scalars()}
    if not pattern_by_dow:
        return

    existing_result = await session.execute(
        select(PlannedWorkout.scheduled_for).where(
            PlannedWorkout.user_id == user_sub,
            PlannedWorkout.scheduled_for.between(start, end),
        )
    )
    existing_dates = {row[0] for row in existing_result.all()}

    templates: dict[uuid.UUID, workout_templates.TemplateOut] = {}
    day = start
    while day <= end:
        template_id = _pattern_template_id(pattern_by_dow, day)
        if day in existing_dates or template_id is None:
            day += timedelta(days=1)
            continue

        template = templates.get(template_id)
        if template is None:
            template = await workout_templates._load_template(session, template_id)
            templates[template_id] = template
        # A day whose pattern template has since been archived generates nothing —
        # treated like a rest day rather than scheduling something no longer usable.
        if template.archived_at is None:
            session.add(
                PlannedWorkout(
                    user_id=user_sub,
                    template_id=template_id,
                    scheduled_for=day,
                    status=PlannedWorkoutStatus.planned,
                )
            )
        day += timedelta(days=1)
    await session.flush()


def _pattern_template_id(
    pattern_by_dow: dict[int, WeeklyPatternDay], day: date
) -> uuid.UUID | None:
    pattern_day = pattern_by_dow.get(day.weekday())
    return pattern_day.template_id if pattern_day is not None else None


async def get_planned_workouts(
    session: AsyncSession, user_sub: str, *, start: date, end: date
) -> list[PlannedWorkoutOut]:
    """Generates any missing dates in range from the weekly pattern, then reads —
    idempotent (a date with any existing row, generated or manually `plan_workout`-
    ed, is left alone). A pattern edit can still reach an already-materialized date
    here, but only one nothing's happened to yet — see `set_weekly_pattern`'s
    `_resync_untouched_planned`."""
    await _generate_missing(session, user_sub, start, end)

    result = await session.execute(
        select(PlannedWorkout)
        .where(PlannedWorkout.user_id == user_sub, PlannedWorkout.scheduled_for.between(start, end))
        .order_by(PlannedWorkout.scheduled_for)
    )
    planned = list(result.scalars())
    templates: dict[uuid.UUID, workout_templates.TemplateOut] = {}
    out = []
    for p in planned:
        template = templates.get(p.template_id)
        if template is None:
            template = await workout_templates._load_template(session, p.template_id)
            templates[p.template_id] = template
        out.append(_to_planned_out(p, template))
    return out


async def get_today_planned(
    session: AsyncSession, user_sub: str, *, tz: ZoneInfo | None = None
) -> PlannedWorkoutOut | None:
    """Today's planned entry, only if it's still unstarted (status "planned") — lets
    the in-workout view's "Start workout" offer starting from today's plan alongside
    starting from scratch. None once the day's plan is done, skipped, or there was
    never one. "Today" is the caller's local date (stored profile zone by default)."""
    tz = tz or await profile_service.get_user_timezone(session, user_sub)
    today = today_in(tz)
    planned = await get_planned_workouts(session, user_sub, start=today, end=today)
    return next((p for p in planned if p.status == PlannedWorkoutStatus.planned), None)


async def _require_planned(
    session: AsyncSession, user_sub: str, planned_id: uuid.UUID
) -> PlannedWorkout:
    result = await session.execute(
        select(PlannedWorkout).where(
            PlannedWorkout.id == planned_id, PlannedWorkout.user_id == user_sub
        )
    )
    planned = result.scalar_one_or_none()
    if planned is None:
        raise NotFoundError(f"No planned workout {planned_id}")
    return planned


async def get_planned_workout(
    session: AsyncSession, user_sub: str, planned_id: uuid.UUID
) -> PlannedWorkoutOut:
    """Ownership-checked single read — `workouts.start_workout(planned_id=...)`
    calls this first to resolve which template to start from and to validate the
    entry is the caller's."""
    planned = await _require_planned(session, user_sub, planned_id)
    template = await workout_templates._load_template(session, planned.template_id)
    return _to_planned_out(planned, template)


async def update_planned_workout(
    session: AsyncSession, user_sub: str, *, planned_id: uuid.UUID, action: str
) -> PlannedWorkoutOut:
    """Actions: "skip" (only from a not-yet-started planned entry), "unskip". No
    "remove" — the doc is explicit that rows are never deleted, only status-changed
    (that's what lets the row count double as the streak target in a later slice)."""
    planned = await _require_planned(session, user_sub, planned_id)
    if action == "skip":
        if planned.status != PlannedWorkoutStatus.planned or planned.workout_id is not None:
            raise ValueError("Only a not-yet-started planned workout can be skipped.")
        planned.status = PlannedWorkoutStatus.skipped
    elif action == "unskip":
        if planned.status != PlannedWorkoutStatus.skipped:
            raise ValueError("Only a skipped planned workout can be unskipped.")
        planned.status = PlannedWorkoutStatus.planned
    else:
        raise ValueError(f"Unknown action: {action!r}")

    await session.flush()
    template = await workout_templates._load_template(session, planned.template_id)
    return _to_planned_out(planned, template)


async def link_workout(session: AsyncSession, planned_id: uuid.UUID, workout_id: uuid.UUID) -> None:
    """Called by `workouts.start_workout` right after `get_planned_workout` already
    validated ownership — no re-check here."""
    result = await session.execute(select(PlannedWorkout).where(PlannedWorkout.id == planned_id))
    planned = result.scalar_one_or_none()
    if planned is not None:
        planned.workout_id = workout_id


async def mark_done_if_planned(session: AsyncSession, workout_id: uuid.UUID) -> None:
    """Called by `workouts.finish_workout` — a no-op if this workout wasn't started
    from a planned entry."""
    result = await session.execute(
        select(PlannedWorkout).where(PlannedWorkout.workout_id == workout_id)
    )
    for planned in result.scalars():
        planned.status = PlannedWorkoutStatus.done
