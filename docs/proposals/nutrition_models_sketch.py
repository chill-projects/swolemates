"""SKETCH ONLY — illustrative SQLAlchemy/Pydantic shapes for docs/proposals/nutrition-v1.md.

Not imported by anything; deliberately outside backend/app. Follows the TmpX conventions
(Base + TimestampMixin, user_id = WorkOS sub string, service-layer scoping).
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin  # illustrative import


# --------------------------------------------------------------------------- tables


class TrackableType(Base, TimestampMixin):
    """Registry of things that can be tracked. New trackable = new ROW, not migration.

    Built-ins ('food', 'water', 'creatine') are seeded by migration; users add more via
    the `define_trackable` tool (created_by = their sub).
    """

    __tablename__ = "trackable_types"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # food|hydration|supplement|other
    unit: Mapped[str] = mapped_column(String(20), nullable=False)  # "g", "ml", "dose", ...
    # Field definitions for GenericPayload validation of non-built-in types.
    payload_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # metric_key -> extraction path, e.g. {"protein_g": "payload.protein_g", "water_ml": "quantity"}
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # e.g. {"metric_key": "water_ml", "direction": "at_least", "target": 2500}
    default_goal: Mapped[dict | None] = mapped_column(JSONB)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str | None] = mapped_column(String(255))  # null for built-ins


class Entry(Base, TimestampMixin):
    """One logged thing, of any trackable type. THE single log table."""

    __tablename__ = "entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    type_key: Mapped[str] = mapped_column(ForeignKey("trackable_types.key"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric, nullable=False)  # in the type's unit
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # typed, see below

    source: Mapped[str] = mapped_column(String(20), nullable=False)  # chat|app|barcode|text_search|photo_ai|template
    source_ref: Mapped[str | None] = mapped_column(String(255))  # barcode / template id / ...
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="confirmed")  # confirmed|draft
    confidence: Mapped[dict | None] = mapped_column(JSONB)  # per-field low|medium|high (photo drafts)
    raw_provider_response: Mapped[dict | None] = mapped_column(JSONB)
    edited_by_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    photo_ref: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (Index("ix_entries_user_id_occurred_at", "user_id", "occurred_at"),)


class Goal(Base, TimestampMixin):
    """A dated goal against a METRIC (not a table). ends_on IS NULL = currently active."""

    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(50), nullable=False)  # "calories", "protein_g", "water_ml", ...
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # at_least|at_most|target
    target: Mapped[float] = mapped_column(Numeric, nullable=False)
    period: Mapped[str] = mapped_column(String(10), nullable=False, default="day")
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (Index("ix_goals_user_id_metric_key", "user_id", "metric_key"),)


class NutritionProfile(Base, TimestampMixin):
    """TDEE inputs (legacy 0008), imperial units. One row per user."""

    __tablename__ = "nutrition_profiles"

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    sex: Mapped[str | None] = mapped_column(String(10))  # male|female
    age: Mapped[int | None] = mapped_column()
    height_in: Mapped[float | None] = mapped_column(Numeric)
    weight_lbs: Mapped[float | None] = mapped_column(Numeric)
    activity_level: Mapped[str | None] = mapped_column(String(20))
    goal_type: Mapped[str | None] = mapped_column(String(20))  # lose_weight|maintain|gain_muscle|recomp


class MealTemplate(Base, TimestampMixin):
    __tablename__ = "meal_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # [{type_key, quantity, payload}, ...] — same validated shapes as Entry.
    items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    __table_args__ = (Index("ix_meal_templates_user_id", "user_id"),)


# ------------------------------------------------- typed payloads (service layer)

Confidence = Literal["low", "medium", "high"]


class FoodPayload(BaseModel):
    kind: Literal["food"] = "food"
    name: str
    brand: str | None = None
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"] | None = None
    serving_description: str | None = None
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float | None = None  # nullable per legacy 0005; treated as 0 in totals


class WaterPayload(BaseModel):
    kind: Literal["water"] = "water"
    # quantity (ml) on the Entry is the whole story


class SupplementPayload(BaseModel):
    kind: Literal["supplement"] = "supplement"
    dose_description: str | None = None  # "1 scoop (5g)"


class GenericPayload(BaseModel):
    """User-defined trackables: validated against TrackableType.payload_schema at runtime."""

    kind: Literal["generic"] = "generic"
    notes: str | None = None


EntryPayload = Annotated[
    Union[FoodPayload, WaterPayload, SupplementPayload, GenericPayload],
    Field(discriminator="kind"),
]

# services/nutrition.py maps type_key -> payload class ('creatine' and other supplement
# registry rows -> SupplementPayload; unknown/user-defined -> GenericPayload) and
# validates on every write. Adding a rich payload for a new type is a code change;
# tracking it at all is just a TrackableType row.


# ------------------------------------------------- photo estimation (provider-abstract)


class FoodEstimateItem(BaseModel):
    name: str
    serving_description: str
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    confidence: dict[str, Confidence]  # per-field, incl. serving_description


class FoodEstimate(BaseModel):
    items: list[FoodEstimateItem]
    overall_confidence: Confidence
    assumptions: list[str]


class FoodEstimator:  # Protocol in real code; provider is a separate ticket
    async def estimate(self, image_bytes: bytes, media_type: str) -> FoodEstimate: ...
