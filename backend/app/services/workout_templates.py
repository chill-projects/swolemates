"""Workout templates service (#3, resolved — slice 3a: templates).

Kept separate from `app/services/workouts.py` (already ~780 lines before this) —
mirrors the MCP/REST split (`templates_tools.py`, `api/templates.py`).
`workouts.start_workout` imports `get_workout_template` from here (at call time, to
avoid a circular import — this module imports `_resolve_exercise` from `workouts.py`
at load time, so the reference only works in one direction at import time).
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workouts import Exercise, TemplateExercise, WorkoutTemplate
from app.services.errors import NotFoundError
from app.services.workouts import _resolve_exercise


@dataclass
class TemplateExerciseOut:
    id: uuid.UUID
    exercise_id: uuid.UUID
    exercise_name: str | None
    order_index: int
    superset_group: int | None
    sets: int
    reps: int | None
    seconds: int | None
    weight: Decimal | None
    notes: str | None


@dataclass
class TemplateOut:
    id: uuid.UUID
    name: str
    description: str | None
    archived_at: datetime | None
    exercises: list[TemplateExerciseOut] = field(default_factory=list)


def _validate_template_exercise(
    exercise_name: str, *, sets: int | None, reps: int | None, seconds: int | None
) -> None:
    if not sets or sets <= 0:
        raise ValueError(f"{exercise_name}: needs sets > 0.")
    if (reps is None) == (seconds is None):
        raise ValueError(f"{exercise_name}: needs exactly one of reps or seconds.")


async def _load_template(session: AsyncSession, template_id: uuid.UUID) -> TemplateOut:
    result = await session.execute(select(WorkoutTemplate).where(WorkoutTemplate.id == template_id))
    template = result.scalar_one()
    ex_result = await session.execute(
        select(TemplateExercise, Exercise.name)
        .join(Exercise, Exercise.id == TemplateExercise.exercise_id)
        .where(TemplateExercise.template_id == template_id)
        .order_by(TemplateExercise.order_index)
    )
    exercises = [
        TemplateExerciseOut(
            id=te.id,
            exercise_id=te.exercise_id,
            exercise_name=name,
            order_index=te.order_index,
            superset_group=te.superset_group,
            sets=te.target_sets,
            reps=te.target_reps,
            seconds=te.target_seconds,
            weight=te.target_weight,
            notes=te.notes,
        )
        for te, name in ex_result.all()
    ]
    return TemplateOut(
        id=template.id,
        name=template.name,
        description=template.description,
        archived_at=template.archived_at,
        exercises=exercises,
    )


async def create_workout_template(
    session: AsyncSession, user_sub: str, *, name: str, exercises: list[dict]
) -> TemplateOut:
    """`exercises`: [{"exercise": str, "sets": int, "reps"?: int, "seconds"?: int,
    "weight"?: Decimal, "notes"?: str, "group"?: int}] — exactly one of reps/seconds
    per entry. `group` is caller-supplied: exercises sharing a value become one
    superset in the template (same convention as `update_workout_entry`'s
    `superset_with`, just supplied up front since the whole template is created in
    one call)."""
    if not exercises:
        raise ValueError("A template needs at least one exercise.")
    for entry in exercises:
        _validate_template_exercise(
            entry["exercise"],
            sets=entry.get("sets"),
            reps=entry.get("reps"),
            seconds=entry.get("seconds"),
        )

    template = WorkoutTemplate(user_id=user_sub, name=name)
    session.add(template)
    await session.flush()

    for order, entry in enumerate(exercises):
        resolved = await _resolve_exercise(session, user_sub, entry["exercise"])
        session.add(
            TemplateExercise(
                template_id=template.id,
                exercise_id=resolved.id,
                order_index=order,
                superset_group=entry.get("group"),
                target_sets=entry["sets"],
                target_reps=entry.get("reps"),
                target_seconds=entry.get("seconds"),
                target_weight=entry.get("weight"),
                notes=entry.get("notes"),
            )
        )

    await session.flush()
    return await _load_template(session, template.id)


async def get_workout_template(
    session: AsyncSession, user_sub: str, template_id: uuid.UUID
) -> TemplateOut:
    result = await session.execute(
        select(WorkoutTemplate).where(
            WorkoutTemplate.id == template_id, WorkoutTemplate.user_id == user_sub
        )
    )
    if result.scalar_one_or_none() is None:
        raise NotFoundError(f"No template {template_id}")
    return await _load_template(session, template_id)


async def list_workout_templates(session: AsyncSession, user_sub: str) -> list[TemplateOut]:
    """Excludes archived templates."""
    result = await session.execute(
        select(WorkoutTemplate.id)
        .where(WorkoutTemplate.user_id == user_sub, WorkoutTemplate.archived_at.is_(None))
        .order_by(WorkoutTemplate.created_at.desc())
    )
    return [await _load_template(session, row[0]) for row in result.all()]


async def archive_workout_template(
    session: AsyncSession, user_sub: str, template_id: uuid.UUID
) -> None:
    result = await session.execute(
        select(WorkoutTemplate).where(
            WorkoutTemplate.id == template_id, WorkoutTemplate.user_id == user_sub
        )
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundError(f"No template {template_id}")
    template.archived_at = datetime.now(UTC)
    await session.flush()


async def _require_template(
    session: AsyncSession, user_sub: str, template_id: uuid.UUID
) -> WorkoutTemplate:
    result = await session.execute(
        select(WorkoutTemplate).where(
            WorkoutTemplate.id == template_id, WorkoutTemplate.user_id == user_sub
        )
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundError(f"No template {template_id}")
    if template.archived_at is not None:
        raise ValueError("This template is archived.")
    return template


async def _next_template_superset_group(session: AsyncSession, template_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.max(TemplateExercise.superset_group)).where(
            TemplateExercise.template_id == template_id
        )
    )
    return (result.scalar_one_or_none() or 0) + 1


async def update_workout_template(
    session: AsyncSession,
    user_sub: str,
    *,
    template_id: uuid.UUID,
    action: str,
    name: str | None = None,
    exercise: str | None = None,
    template_exercise_id: uuid.UUID | None = None,
    superset_with: uuid.UUID | None = None,
    order: list[uuid.UUID] | None = None,
    sets: int | None = None,
    reps: int | None = None,
    seconds: int | None = None,
    weight: Decimal | None = None,
    notes: str | None = None,
) -> TemplateOut:
    """One entry point, dispatched on `action` — driven by discrete buttons in
    `template.html`, same shape as `workouts.update_workout_entry`.

    Actions: "rename" (name), "add_exercise" (exercise, sets, reps/seconds, weight?,
    notes?, superset_with?), "remove_exercise" (template_exercise_id — only if it's
    not referenced elsewhere, though templates have no such reference today),
    "reorder_exercises" (order — every current template_exercise_id, in the new
    order), "update_exercise" (template_exercise_id, plus whichever of
    sets/reps/seconds/weight/notes changed — only passed fields are touched).
    """
    template = await _require_template(session, user_sub, template_id)

    if action == "rename":
        if not name:
            raise ValueError("rename needs 'name'.")
        template.name = name
    elif action == "add_exercise":
        if exercise is None:
            raise ValueError("add_exercise needs 'exercise'.")
        _validate_template_exercise(exercise, sets=sets, reps=reps, seconds=seconds)
        resolved = await _resolve_exercise(session, user_sub, exercise)
        count_result = await session.execute(
            select(func.count(TemplateExercise.id)).where(
                TemplateExercise.template_id == template.id
            )
        )
        group = None
        if superset_with is not None:
            partner = await session.get(TemplateExercise, superset_with)
            if partner is None or partner.template_id != template.id:
                raise NotFoundError("No such exercise in this template.")
            if partner.superset_group is None:
                partner.superset_group = await _next_template_superset_group(session, template.id)
            group = partner.superset_group
        session.add(
            TemplateExercise(
                template_id=template.id,
                exercise_id=resolved.id,
                order_index=count_result.scalar_one() or 0,
                superset_group=group,
                target_sets=sets,
                target_reps=reps,
                target_seconds=seconds,
                target_weight=weight,
                notes=notes,
            )
        )
    elif action == "remove_exercise":
        if template_exercise_id is None:
            raise ValueError("remove_exercise needs 'template_exercise_id'.")
        te = await session.get(TemplateExercise, template_exercise_id)
        if te is None or te.template_id != template.id:
            raise NotFoundError("No such exercise in this template.")
        await session.execute(delete(TemplateExercise).where(TemplateExercise.id == te.id))
    elif action == "reorder_exercises":
        if not order:
            raise ValueError("reorder_exercises needs 'order'.")
        result = await session.execute(
            select(TemplateExercise).where(TemplateExercise.template_id == template.id)
        )
        existing = {te.id: te for te in result.scalars()}
        if set(order) != set(existing):
            raise ValueError("'order' must include exactly this template's current exercises.")
        for index, te_id in enumerate(order):
            existing[te_id].order_index = index
    elif action == "update_exercise":
        if template_exercise_id is None:
            raise ValueError("update_exercise needs 'template_exercise_id'.")
        te = await session.get(TemplateExercise, template_exercise_id)
        if te is None or te.template_id != template.id:
            raise NotFoundError("No such exercise in this template.")
        if sets is not None:
            te.target_sets = sets
        if reps is not None:
            te.target_reps = reps
        if seconds is not None:
            te.target_seconds = seconds
        if weight is not None:
            te.target_weight = weight
        if notes is not None:
            te.notes = notes
    else:
        raise ValueError(f"Unknown action: {action!r}")

    await session.flush()
    return await _load_template(session, template.id)
