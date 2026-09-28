from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PlannedMealOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scheduled_for: date
    meal_type: str
    name: str
    source: str
    template_id: UUID | None
    kitchen_item_id: UUID | None
    portion: Decimal | None
    status: str
    log_group_id: UUID | None
    values: dict[str, Decimal]
    #: False when this meal's macros are genuinely unknown, which is not the same as
    #: zero — the SPA shows "not estimated" rather than a number.
    estimated: bool
    overridden: bool


class PlannedDayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scheduled_for: date
    meals: list[PlannedMealOut]
    totals: dict[str, Decimal]
    unestimated: int


class PlanMealRequest(BaseModel):
    scheduled_for: date
    meal_type: str
    template_id: UUID | None = None
    kitchen_item_id: UUID | None = None
    name: str | None = None
    portion: Decimal | None = None
    values: dict[str, Decimal] | None = None


class UpdatePlannedMealRequest(BaseModel):
    """Every field optional; only what's sent changes.

    `values` has three meanings, which is deliberate and matches
    `update_meal_template`'s handling of an empty tag: absent leaves the macros alone,
    a populated dict overrides them, and `{}` clears the override so they fall back to
    whatever the meal came from.
    """

    name: str | None = None
    portion: Decimal | None = None
    values: dict[str, Decimal] | None = None
    scheduled_for: date | None = None
    meal_type: str | None = None


class KitchenTemplateRefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class KitchenItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    name: str
    portion: Decimal | None
    #: Already scaled by `portion` — what this is worth now, not what it started as.
    values: dict[str, Decimal]
    templates: list[KitchenTemplateRefOut]


class AddKitchenItemRequest(BaseModel):
    kind: str
    name: str
    portion: Decimal | None = None
    values: dict[str, Decimal] | None = None
    template_ids: list[UUID] | None = None


class UpdateKitchenItemRequest(BaseModel):
    name: str | None = None
    portion: Decimal | None = None
