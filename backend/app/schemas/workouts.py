from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.workouts import SetType, WorkoutType


class SetIn(BaseModel):
    set_type: str = "reps"
    weight: Decimal | None = None
    reps: int | None = None
    work_seconds: int | None = None
    is_warmup: bool = False


class ExerciseEntryIn(BaseModel):
    exercise: str
    sets: list[SetIn] = Field(min_length=1)
    notes: str | None = None
    next_time_note: str | None = None
    muscle_group: str | None = None


class LogWorkoutRequest(BaseModel):
    exercises: list[ExerciseEntryIn] = Field(min_length=1)
    title: str | None = None
    notes: str | None = None
    logged_at: datetime | None = None


class LogActivityRequest(BaseModel):
    activity_type: str
    duration_minutes: int
    title: str | None = None
    notes: str | None = None
    logged_at: datetime | None = None


class StartWorkoutRequest(BaseModel):
    exercises: list[str] | None = None
    template_id: UUID | None = None


class LogSetRequest(BaseModel):
    exercise: str
    reps: int | None = None
    weight: Decimal | None = None
    set_type: str = "reps"
    work_seconds: int | None = None
    is_warmup: bool = False
    sets: int = 1
    note: str | None = None
    continue_session: bool | None = None


class FinishWorkoutRequest(BaseModel):
    notes: str | None = None


class SetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    set_number: int
    set_type: SetType
    is_warmup: bool
    weight: Decimal | None
    reps: int | None
    work_seconds: int | None


class LastTimeSetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    weight: Decimal | None
    reps: int | None


class LastTimeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sets: list[LastTimeSetOut]
    note: str | None


class TargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sets: int
    reps: int | None
    seconds: int | None
    weight: Decimal | None


class ExerciseEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    exercise_id: UUID
    exercise_name: str | None
    notes: str | None
    next_time_note: str | None
    sets: list[SetOut]
    superset_group: int | None = None
    last_time: LastTimeOut | None = None
    target: TargetOut | None = None


class WorkoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workout_type: WorkoutType
    activity_type: str | None
    duration_minutes: int | None
    title: str | None
    notes: str | None
    started_at: datetime
    completed_at: datetime | None
    exercises: list[ExerciseEntryOut]
    resumed: bool = False


class LogSetResponse(BaseModel):
    workout: WorkoutOut | None = None
    needs_clarification: str | None = None


class WorkoutGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    superset_group: int | None
    is_superset: bool
    exercises: list[ExerciseEntryOut]


class WorkoutLiveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    started_at: datetime
    completed_at: datetime | None
    notes: str | None
    groups: list[WorkoutGroupOut]
    summary: str


class UpdateWorkoutEntryRequest(BaseModel):
    action: str
    exercise: str | None = None
    workout_exercise_id: UUID | None = None
    superset_with: UUID | None = None
    order: list[UUID] | None = None
    note: str | None = None


class ExerciseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    muscle_group: str
