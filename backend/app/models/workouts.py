"""Workouts core (#3, resolved — slice 1 of 5: core domain model + one-shot logging).

`template_id` on `Workout` and `superset_group` on `WorkoutExercise` are deliberately
left out — they land in later slices (templates/plans, in-workout mode) as additive
migrations exactly when those slices need them, same pattern as nutrition's
`group_id`/`group_name`.
"""

import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class WorkoutType(enum.StrEnum):
    strength = "strength"
    activity = "activity"


class SetType(enum.StrEnum):
    reps = "reps"
    time = "time"


class Exercise(Base, TimestampMixin):
    """Catalog (seeded from the 41 legacy starters; free-exercise-db's full 873-
    exercise vendoring is a separate follow-up) + user custom exercises.

    Read rule in the service layer: `is_custom == False OR created_by == user_sub`
    (port of the legacy RLS policy).
    """

    __tablename__ = "exercises"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    muscle_group: Mapped[str] = mapped_column(String(50), nullable=False)
    equipment: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    image_paths: Mapped[list | None] = mapped_column(JSONB)
    source_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str | None] = mapped_column(String(255))


class Workout(Base, TimestampMixin):
    """One session, strength or activity. `completed_at IS NULL` means in-progress —
    not reachable in slice 1 (no in-workout mode yet), but the column stays nullable
    now so slice 2 doesn't need a later migration to relax it.
    """

    __tablename__ = "workouts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    workout_type: Mapped[WorkoutType] = mapped_column(
        Enum(WorkoutType, name="workout_type"), nullable=False, default=WorkoutType.strength
    )
    activity_type: Mapped[str | None] = mapped_column(String(100))
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "(workout_type = 'strength' AND activity_type IS NULL AND duration_minutes IS NULL)"
            " OR (workout_type = 'activity' AND activity_type IS NOT NULL"
            "     AND duration_minutes IS NOT NULL)",
            name="ck_workouts_workout_type_fields_check",
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
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    # "notes-for-next-time": surfaced next time this exercise comes up (later
    # slices' planned view / in-workout mode show the most recent one per exercise)
    next_time_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_workout_exercises_workout_id", "workout_id"),)


class WorkoutSet(Base):
    """`prescribed_*` stays unused until slice 3 (templates) copies targets in at
    session start. For slice 1's one-shot `log_workout`, only `actual_*` is written
    and `completed_at` is set immediately (no in-progress state yet).
    """

    __tablename__ = "workout_sets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workout_exercise_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workout_exercises.id", ondelete="CASCADE"), nullable=False
    )
    set_number: Mapped[int] = mapped_column(Integer, nullable=False)
    set_type: Mapped[SetType] = mapped_column(
        Enum(SetType, name="set_type"), nullable=False, default=SetType.reps
    )
    is_warmup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prescribed_weight: Mapped[object | None] = mapped_column(Numeric)
    prescribed_reps: Mapped[int | None] = mapped_column(Integer)
    actual_weight: Mapped[object | None] = mapped_column(Numeric)
    actual_reps: Mapped[int | None] = mapped_column(Integer)
    work_seconds: Mapped[int | None] = mapped_column(Integer)
    rest_seconds: Mapped[int | None] = mapped_column(Integer)
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "completed_at IS NULL"
            " OR (set_type = 'reps' AND actual_reps IS NOT NULL)"
            " OR (set_type = 'time' AND work_seconds IS NOT NULL)",
            name="ck_workout_sets_set_type_fields_check",
        ),
        Index("ix_workout_sets_workout_exercise_id", "workout_exercise_id"),
    )
