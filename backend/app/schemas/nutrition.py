from datetime import date, datetime
from decimal import Decimal
from typing import Literal
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


class UpdateNutritionLogRequest(BaseModel):
    name: str | None = None
    meal_type: str | None = None
    values: dict[str, Decimal] | None = None


class NutritionLogOut(BaseModel):
    id: UUID
    name: str | None
    logged_at: datetime
    meal_type: str | None
    values: dict[str, Decimal]


class AmendLastLogOut(BaseModel):
    deleted: bool
    log: NutritionLogOut | None = None


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


class TrackableProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trackable_key: str
    label: str
    unit: str
    consumed: Decimal
    target: Decimal | None


class DayLogItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str | None
    values: dict[str, Decimal]


class DayLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str | None
    logged_at: datetime
    meal_type: str | None
    values: dict[str, Decimal]
    items: list[DayLogItemOut]


class MealTemplateItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    serving_description: str | None
    values: dict[str, Decimal]


class MealTemplateSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    default_meal_type: str | None
    items: list[MealTemplateItemOut]
    totals: dict[str, Decimal]


class NutritionDayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    hero: TrackableProgressOut
    bars: list[TrackableProgressOut]
    streak_key: str | None
    logs: list[DayLogOut]
    templates: list[MealTemplateSummaryOut]


class NutritionCalendarDayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    status: Literal["hit", "miss", "no-data"]
    hero: TrackableProgressOut
    bars: list[TrackableProgressOut]


class SaveMealTemplateRequest(BaseModel):
    name: str
    log_ids: list[UUID] = Field(min_length=1)
    default_meal_type: str | None = None
    template_id: UUID | None = None


class LogMealTemplateRequest(BaseModel):
    multiplier: Decimal = Decimal(1)
    meal_type: str | None = None
    logged_at: datetime | None = None


class UpdateMealTemplateItemRequest(BaseModel):
    name: str
    serving_description: str | None = None
    values: dict[str, Decimal] = Field(default_factory=dict)
