from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.workouts import PersonalRecordKind
from app.schemas.workouts import StreakOut


class PartnerInviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    expires_at: datetime


class InvitePreviewOut(BaseModel):
    inviter_display_name: str | None
    valid: bool


class RedeemInviteRequest(BaseModel):
    code: str


class PartnerFrequencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workouts_last_7_days: int
    workouts_last_30_days: int
    total_workouts: int
    last_workout_at: datetime | None


class PartnerPersonalRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    exercise_name: str
    kind: PersonalRecordKind
    value: Decimal
    achieved_at: datetime


class PartnerSummaryOut(BaseModel):
    """The privacy boundary itself (#12, resolved) — every field here is an
    aggregate value. There is no field food logs or weight entries could travel
    through, so a careless future change to `services/partner.py` has nowhere to
    put that data even by accident."""

    model_config = ConfigDict(from_attributes=True)

    partner_display_name: str | None
    streak: StreakOut
    frequency: PartnerFrequencyOut
    nutrition_streak: int
    personal_records: list[PartnerPersonalRecordOut]
