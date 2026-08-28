from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.profile import ActivityLevel, BiologicalSex, GoalType, WeightUnit


class ProfileUpdate(BaseModel):
    weight_unit: WeightUnit | None = None
    coach_notes: str | None = Field(default=None, max_length=4000)
    sex: BiologicalSex | None = None
    age: int | None = Field(default=None, gt=0, lt=120)
    height_in: Decimal | None = None
    activity_level: ActivityLevel | None = None
    goal_type: GoalType | None = None
    timezone: str | None = Field(default=None, max_length=64)


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    weight_unit: WeightUnit
    coach_notes: str | None
    onboarding_completed_at: datetime | None
    sex: BiologicalSex | None
    age: int | None
    height_in: Decimal | None
    activity_level: ActivityLevel | None
    goal_type: GoalType | None
    timezone: str | None
