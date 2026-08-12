from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.profile import WeightUnit


class ProfileUpdate(BaseModel):
    weight_unit: WeightUnit | None = None
    coach_notes: str | None = Field(default=None, max_length=4000)


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    weight_unit: WeightUnit
    coach_notes: str | None
    onboarding_completed_at: datetime | None
