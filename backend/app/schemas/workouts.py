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


class SetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    set_number: int
    set_type: SetType
    is_warmup: bool
    weight: Decimal | None
    reps: int | None
    work_seconds: int | None


class ExerciseEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    exercise_id: UUID
    exercise_name: str | None
    notes: str | None
    next_time_note: str | None
    sets: list[SetOut]


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
