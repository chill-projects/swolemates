"""Workouts core (#3, resolved — slice 1 of 5: core domain model + one-shot logging).

`template_id` on `Workout` is deliberately left out — it lands in a later slice
(templates/plans) as an additive migration exactly when that slice needs it, same
pattern as nutrition's `group_id`/`group_name`. `superset_group` on `WorkoutExercise`
landed in slice 2b, once the in-workout accordion actually grouped by it.
`WorkoutTemplate`/`TemplateExercise` and `WorkoutExercise.target_*` landed in slice 3a.
`WeeklyPatternDay`/`PlannedWorkout` landed in slice 3b. `PersonalRecord` landed in
slice 4.
"""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
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


class PlannedWorkoutStatus(enum.StrEnum):
    planned = "planned"
    done = "done"
    skipped = "skipped"


class PersonalRecordKind(enum.StrEnum):
    weight = "weight"
    e1rm = "e1rm"


class Exercise(Base, TimestampMixin):
    """Catalog: the 41 legacy starters plus free-exercise-db's full 873-exercise
    vendor (metadata only — names + muscles, no photos; `app/data/exercise_muscles.json`,
    matched via the migration that added `primary_muscles`/`secondary_muscles`), plus
    user custom exercises.

    `muscle_group` (the coarse 6-bucket legacy taxonomy) stays the source of truth for
    anything written before this vendor and for custom exercises (which get no
    primary/secondary muscle data — `_resolve_exercise`'s auto-create path only ever
    sets `muscle_group`). `primary_muscles`/`secondary_muscles` (free-exercise-db's
    17-muscle taxonomy) are additive and only populated for vendored/starter rows —
    the live-workout muscle map reads these, falling back to nothing for custom
    exercises rather than guessing.

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
    primary_muscles: Mapped[list | None] = mapped_column(JSONB)
    secondary_muscles: Mapped[list | None] = mapped_column(JSONB)
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
    # MET-formula fallback for calories burned — set only where a real duration
    # exists (log_activity, finish_workout); "estimated" is the only value today,
    # left as a plain string (not a DB enum) so a later Apple Watch/Health Auto
    # Export source doesn't need an enum-alter migration (#24, deferred).
    calories_burned: Mapped[Decimal | None] = mapped_column(Numeric)
    calories_source: Mapped[str | None] = mapped_column(String(30))

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
    # Null = solo exercise. Exercises sharing a value (and workout) are one superset,
    # worked back-to-back before the shared rest — an arbitrary int scoped to the
    # workout, not a global id.
    superset_group: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    # "notes-for-next-time": surfaced next time this exercise comes up (later
    # slices' planned view / in-workout mode show the most recent one per exercise)
    next_time_note: Mapped[str | None] = mapped_column(Text)
    # Copied from TemplateExercise by start_workout(template_id=...); null for ad-hoc
    # exercises. Per-exercise, not per-set (the resolved doc's "uniform sets x reps @
    # weight" decision) — deliberately not WorkoutSet.prescribed_*, which predates
    # that decision and stays unused.
    target_sets: Mapped[int | None] = mapped_column(Integer)
    target_reps: Mapped[int | None] = mapped_column(Integer)
    target_seconds: Mapped[int | None] = mapped_column(Integer)
    target_weight: Mapped[object | None] = mapped_column(Numeric)

    __table_args__ = (Index("ix_workout_exercises_workout_id", "workout_id"),)


class WorkoutSet(Base):
    """`prescribed_*` predates the resolved doc's decision that a template's
    prescription is uniform per *exercise*, not per set — that decision landed on
    `WorkoutExercise.target_*` instead (slice 3a), so these columns stay unused. Only
    `actual_*` is written, when a set is logged.
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


class WorkoutTemplate(Base, TimestampMixin):
    """A prescription — "Pull day" — created conversationally, started from, and
    edited in place (chat + SPA share one `ui://template.html` component). Removal
    is archiving, not deleting: `archived_at IS NOT NULL` excludes it from listing.
    """

    __tablename__ = "workout_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_workout_templates_user_id", "user_id"),)


class TemplateExercise(Base):
    """One exercise's uniform prescription within a template — `target_sets` sets of
    `target_reps` reps (or `target_seconds` for timed) at `target_weight`. Copied onto
    `WorkoutExercise.target_*` by `start_workout(template_id=...)`; editing the
    template afterward never rewrites a past session's copy.
    """

    __tablename__ = "template_exercises"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workout_templates.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exercises.id"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    superset_group: Mapped[int | None] = mapped_column(Integer)
    target_sets: Mapped[int] = mapped_column(Integer, nullable=False)
    target_reps: Mapped[int | None] = mapped_column(Integer)
    target_seconds: Mapped[int | None] = mapped_column(Integer)
    target_weight: Mapped[object | None] = mapped_column(Numeric)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_template_exercises_template_id", "template_id"),)


class WeeklyPatternDay(Base):
    """The standing split — "Monday is legs, Tuesday is pool." At most one row per
    `(user_id, day_of_week)`; `set_weekly_pattern` replaces the caller's whole set at
    once. `template_id IS NULL` means a rest day. Editing this only affects weeks
    `get_planned_workouts` generates *after* the edit — already-materialized
    `PlannedWorkout` rows are independent and don't retroactively change.
    """

    __tablename__ = "weekly_pattern"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workout_templates.id", ondelete="CASCADE")
    )

    __table_args__ = (
        UniqueConstraint("user_id", "day_of_week", name="uq_weekly_pattern_user_id_day_of_week"),
        CheckConstraint(
            "day_of_week >= 0 AND day_of_week <= 6", name="ck_weekly_pattern_day_of_week"
        ),
    )


class PlannedWorkout(Base):
    """One concrete scheduled session, materialized from `WeeklyPatternDay` for an
    upcoming week (or added directly via `plan_workout`, e.g. "an extra session").
    Rows are never deleted, only status-changed — the row count for a week is what
    slice 4's streak target reads from, so it can't shrink just because a session
    gets skipped later. `workout_id` is set by `start_workout(planned_id=...)`;
    `finish_workout` flips `status` to `done` once that workout completes.
    """

    __tablename__ = "planned_workouts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workout_templates.id", ondelete="CASCADE"), nullable=False
    )
    scheduled_for: Mapped[object] = mapped_column(Date, nullable=False)
    status: Mapped[PlannedWorkoutStatus] = mapped_column(
        Enum(PlannedWorkoutStatus, name="planned_workout_status"),
        nullable=False,
        default=PlannedWorkoutStatus.planned,
    )
    workout_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workouts.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_planned_workouts_user_id_scheduled_for", "user_id", "scheduled_for"),
    )


class PersonalRecord(Base):
    """A mutable *current-record* cache, not an append-only log (the doc's resolved
    decision #4) — one row per `(user_id, exercise_id, kind)`, upserted in place
    whenever `log_set`/`log_workout` writes a set that beats it. If the achieving set
    is later edited or deleted, this should be recomputed from the remaining sets —
    that hook needs `update_workout` (slice 5) and isn't built yet; today a record
    only ever moves forward.
    """

    __tablename__ = "personal_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exercises.id"), nullable=False)
    kind: Mapped[PersonalRecordKind] = mapped_column(
        Enum(PersonalRecordKind, name="personal_record_kind"), nullable=False
    )
    value: Mapped[object] = mapped_column(Numeric, nullable=False)
    workout_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workout_sets.id", ondelete="CASCADE"), nullable=False
    )
    achieved_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "exercise_id", "kind", name="uq_personal_records_user_id_exercise_id_kind"
        ),
    )
