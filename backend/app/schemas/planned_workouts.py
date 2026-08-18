from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.workouts import PlannedWorkoutStatus


class WeeklyPatternDayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day_of_week: int
    template_id: UUID | None
    template_name: str | None


class WeeklyPatternDayIn(BaseModel):
    day_of_week: int
    template_id: UUID | None = None


class SetWeeklyPatternRequest(BaseModel):
    days: list[WeeklyPatternDayIn]


class PlannedWorkoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_id: UUID
    template_name: str
    scheduled_for: date
    status: PlannedWorkoutStatus
    workout_id: UUID | None
    note: str | None
    exercise_names: list[str]


class PlanWorkoutRequest(BaseModel):
    template_id: UUID
    scheduled_for: date


class UpdatePlannedWorkoutRequest(BaseModel):
    action: str
