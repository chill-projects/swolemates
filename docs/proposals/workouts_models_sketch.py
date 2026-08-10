"""SKETCH ONLY — companion to workouts-v1.md (ticket #3 prototype).

Not imported anywhere, not under backend/app, not picked up by Alembic. A reaction
artifact: the §2 domain model written as SQLAlchemy so the shapes are concrete.
Follows the tmpx conventions: user_id is the WorkOS `sub` (String(255), no FK),
scoping happens in the service layer, TimestampMixin adds created_at/updated_at.
"""

import enum
import uuid

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

# In the real slice these come from app.models.base
from app.models.base import Base, TimestampMixin  # type: ignore  # sketch


class WorkoutType(enum.StrEnum):
    strength = "strength"
    activity = "activity"


class ActivityType(enum.StrEnum):
    yoga = "yoga"
    pilates = "pilates"
    cardio = "cardio"
    other = "other"


class SetType(enum.StrEnum):
    reps = "reps"
    time = "time"


class PlanStatus(enum.StrEnum):
    planned = "planned"
    done = "done"
    skipped = "skipped"


class PRKind(enum.StrEnum):
    weight = "weight"          # heaviest weight ever for the exercise
    e1rm = "e1rm"              # best Epley estimated 1RM
    reps_at_weight = "reps_at_weight"


class Exercise(Base, TimestampMixin):
    """Catalog (seeded from free-exercise-db per #15) + user custom exercises."""

    __tablename__ = "exercises"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    muscle_group: Mapped[str] = mapped_column(String(50), nullable=False)
    equipment: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)          # joined instructions
    image_paths: Mapped[list | None] = mapped_column(JSONB)        # same-origin static paths
    source_id: Mapped[str | None] = mapped_column(String(100), unique=True)  # free-exercise-db id
    is_custom: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_by: Mapped[str | None] = mapped_column(String(255))    # WorkOS sub, custom only
    # service read rule: is_custom == False OR created_by == user_sub


class WorkoutTemplate(Base, TimestampMixin):
    __tablename__ = "workout_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_workout_templates_user_id", "user_id"),)


class TemplateExercise(Base):
    """Uniform prescription per exercise (4x8 @ 60) — per-set detail is OQ 2."""

    __tablename__ = "template_exercises"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workout_templates.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exercises.id"), nullable=False)
    order_index: Mapped[int] = mapped_column(nullable=False, default=0)
    # null = solo exercise; rows sharing a group are a superset, worked back-to-back
    superset_group: Mapped[int | None] = mapped_column()
    target_sets: Mapped[int] = mapped_column(nullable=False)
    target_reps: Mapped[int | None] = mapped_column()
    target_seconds: Mapped[int | None] = mapped_column()           # timed work
    target_weight: Mapped[object | None] = mapped_column(Numeric)  # null = "coach's call"
    notes: Mapped[str | None] = mapped_column(Text)


class Workout(Base, TimestampMixin):
    """One session. completed_at IS NULL == in-progress (the in-workout-mode state)."""

    __tablename__ = "workouts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    workout_type: Mapped[WorkoutType] = mapped_column(
        Enum(WorkoutType), nullable=False, default=WorkoutType.strength
    )
    activity_type: Mapped[ActivityType | None] = mapped_column(Enum(ActivityType))
    duration_minutes: Mapped[int | None] = mapped_column()
    title: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workout_templates.id", ondelete="SET NULL")
    )

    __table_args__ = (
        # ported from legacy 0004
        CheckConstraint(
            "(workout_type = 'strength' AND activity_type IS NULL AND duration_minutes IS NULL)"
            " OR (workout_type = 'activity' AND activity_type IS NOT NULL"
            "     AND duration_minutes IS NOT NULL)",
            name="workout_type_fields_check",
        ),
        Index("ix_workouts_user_id_started_at", "user_id", "started_at"),
    )


class WorkoutExercise(Base):
    __tablename__ = "workout_exercises"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workout_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workouts.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exercises.id"), nullable=False)
    order_index: Mapped[int] = mapped_column(nullable=False, default=0)
    # copied from template_exercises.superset_group by start_workout
    superset_group: Mapped[int | None] = mapped_column()
    notes: Mapped[str | None] = mapped_column(Text)
    # "notes-for-next-time": surfaced next time this exercise appears (planned view
    # and in-workout mode show the most recent one per exercise)
    next_time_note: Mapped[str | None] = mapped_column(Text)


class WorkoutSet(Base):
    """prescribed_* copied from the template at start; actuals logged in-workout.

    completed_at NULL = not yet logged. For completed sets the legacy invariant holds
    (reps sets need actual_reps, timed sets need work_seconds) — enforced by the CHECK
    below plus service-layer validation (workoutValidation.ts port).
    """

    __tablename__ = "workout_sets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workout_exercise_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workout_exercises.id", ondelete="CASCADE"), nullable=False
    )
    set_number: Mapped[int] = mapped_column(nullable=False)
    set_type: Mapped[SetType] = mapped_column(Enum(SetType), nullable=False, default=SetType.reps)
    is_warmup: Mapped[bool] = mapped_column(nullable=False, default=False)
    prescribed_weight: Mapped[object | None] = mapped_column(Numeric)
    prescribed_reps: Mapped[int | None] = mapped_column()
    actual_weight: Mapped[object | None] = mapped_column(Numeric)
    actual_reps: Mapped[int | None] = mapped_column()
    work_seconds: Mapped[int | None] = mapped_column()
    rest_seconds: Mapped[int | None] = mapped_column()
    rpe: Mapped[object | None] = mapped_column(Numeric)
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # legacy 0004 set_type_fields_check, relaxed to completed sets only
        CheckConstraint(
            "completed_at IS NULL"
            " OR (set_type = 'reps' AND actual_reps IS NOT NULL)"
            " OR (set_type = 'time' AND work_seconds IS NOT NULL)",
            name="set_type_fields_check",
        ),
    )


class PlannedWorkout(Base, TimestampMixin):
    """Flat schedule: 'Leg Day on Thursday'. Recurrence deliberately out (OQ 3)."""

    __tablename__ = "planned_workouts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workout_templates.id", ondelete="CASCADE"), nullable=False
    )
    scheduled_for: Mapped[object] = mapped_column(Date, nullable=False)
    status: Mapped[PlanStatus] = mapped_column(
        Enum(PlanStatus), nullable=False, default=PlanStatus.planned
    )
    workout_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workouts.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_planned_workouts_user_id_scheduled_for", "user_id", "scheduled_for"),)


class PersonalRecord(Base, TimestampMixin):
    """Denormalized celebration cache — existence is OQ 4."""

    __tablename__ = "personal_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exercises.id"), nullable=False)
    kind: Mapped[PRKind] = mapped_column(Enum(PRKind), nullable=False)
    value: Mapped[object] = mapped_column(Numeric, nullable=False)  # weight, e1rm, or reps
    weight: Mapped[object | None] = mapped_column(Numeric)          # for reps_at_weight
    reps: Mapped[int | None] = mapped_column()
    workout_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workout_sets.id", ondelete="CASCADE"), nullable=False
    )
    achieved_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_personal_records_user_id_exercise_id", "user_id", "exercise_id"),)
