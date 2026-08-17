from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TemplateExerciseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    exercise_id: UUID
    exercise_name: str | None
    order_index: int
    superset_group: int | None
    sets: int
    reps: int | None
    seconds: int | None
    weight: Decimal | None
    notes: str | None


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    archived_at: datetime | None
    exercises: list[TemplateExerciseOut]


class CreateTemplateExerciseIn(BaseModel):
    exercise: str
    sets: int
    reps: int | None = None
    seconds: int | None = None
    weight: Decimal | None = None
    notes: str | None = None
    group: int | None = None


class CreateWorkoutTemplateRequest(BaseModel):
    name: str
    exercises: list[CreateTemplateExerciseIn]


class UpdateWorkoutTemplateRequest(BaseModel):
    action: str
    name: str | None = None
    exercise: str | None = None
    template_exercise_id: UUID | None = None
    superset_with: UUID | None = None
    order: list[UUID] | None = None
    sets: int | None = None
    reps: int | None = None
    seconds: int | None = None
    weight: Decimal | None = None
    notes: str | None = None
