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


class CheckinDecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    detail: str


class CarriedNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    exercise_name: str
    note: str
    logged_on: date


class WeeklyReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    start: date
    end: date
    sessions_completed: int
    sessions_planned: int
    nutrition_days_logged: int


class UpcomingSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scheduled_for: date
    template_name: str
    status: PlannedWorkoutStatus


class StreakOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    weeks: int
    this_week: int
    target: int


class WeeklyCheckinOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    as_of: date
    review: WeeklyReviewOut
    upcoming: list[UpcomingSessionOut]
    carried_notes: list[CarriedNoteOut]
    decisions: list[CheckinDecisionOut]
    streak: StreakOut | None
    nutrition_streak: int
    summary: str
