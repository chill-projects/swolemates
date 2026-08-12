from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NutritionEntryIn(BaseModel):
    trackable_key: str
    value: Decimal


class LogNutritionRequest(BaseModel):
    entries: list[NutritionEntryIn] = Field(min_length=1)
    logged_at: datetime | None = None
    name: str | None = None
    meal_type: str | None = None
    source: str = "manual"


class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str | None
    logged_at: datetime
    meal_type: str | None


class GoalIn(BaseModel):
    trackable_key: str
    target_value: Decimal
    is_streak_target: bool | None = None


class SetGoalsRequest(BaseModel):
    goals: list[GoalIn] = Field(min_length=1)


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trackable_key: str
    target_value: Decimal
    period: str
    is_streak_target: bool


class TrackableTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    unit: str
    category: str
    goal_eligible: bool
