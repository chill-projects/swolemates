"""Meal plan — the eating half of the Plan tab.

Mirrors the workout side one concept at a time: `PlannedMeal` is to `PlannedWorkout`
what `MealTemplate` is to `WorkoutTemplate`. The differences are the two things meal
planning has that session planning doesn't.

First, a slot. Workouts can stack ("an extra session on Thursday"); eating is arranged
into breakfast/lunch/dinner/snack, so `(user, date, meal_type)` is unique and planning
into a full slot replaces what was there.

Second, provenance. A planned meal is a *forecast*, and the forecast can come from three
places: a saved meal, a leftover sitting in the kitchen, or a name someone typed with no
numbers attached. `PlannedMealValue` exists so the caller can overrule all three — an
edited plan must not be silently rewritten when the saved meal behind it changes.
"""

import enum
import uuid

from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")


class PlannedMealStatus(enum.StrEnum):
    planned = "planned"
    logged = "logged"
    skipped = "skipped"


class KitchenItemKind(enum.StrEnum):
    """What a "needs eating" entry actually is.

    A `leftover` is a portion of a meal that already exists — it carries its own values
    and can be planned straight into a slot. An `ingredient` has no macros of its own;
    it points at the saved meals that use it, and planning means planning one of those.
    """

    leftover = "leftover"
    ingredient = "ingredient"


class KitchenItem(Base, TimestampMixin):
    __tablename__ = "kitchen_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[KitchenItemKind] = mapped_column(
        Enum(KitchenItemKind, name="kitchen_item_kind"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # How much of the original is left, for a leftover. NULL for an ingredient.
    portion: Mapped[object | None] = mapped_column(Numeric)

    __table_args__ = (Index("ix_kitchen_items_user_id", "user_id"),)


class KitchenItemValue(Base):
    """A leftover's macros, snapshotted whole. `portion` scales these at read time
    rather than being baked in, so correcting "actually there's a third left" is one
    column write and not a re-derivation."""

    __tablename__ = "kitchen_item_values"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kitchen_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("kitchen_items.id", ondelete="CASCADE"), nullable=False
    )
    trackable_key: Mapped[str] = mapped_column(ForeignKey("trackable_types.key"), nullable=False)
    value: Mapped[object] = mapped_column(Numeric, nullable=False)

    __table_args__ = (
        Index("ix_kitchen_item_values_kitchen_item_id", "kitchen_item_id"),
        UniqueConstraint(
            "kitchen_item_id", "trackable_key", name="uq_kitchen_item_values_kitchen_item_id"
        ),
    )


class KitchenItemTemplate(Base):
    """Which saved meals use an ingredient — the "to use up half a cabbage, plan one of
    these" link. Only meaningful for `KitchenItemKind.ingredient`."""

    __tablename__ = "kitchen_item_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kitchen_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("kitchen_items.id", ondelete="CASCADE"), nullable=False
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meal_templates.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "kitchen_item_id", "template_id", name="uq_kitchen_item_templates_kitchen_item_id"
        ),
    )


class PlannedMeal(Base, TimestampMixin):
    """One slot on one day.

    `name` is always populated, even when `template_id` is set: it snapshots what the
    meal was called when it was planned, so deleting the saved meal or the leftover
    leaves a plan that still reads sensibly instead of a blank row. Both foreign keys
    are `SET NULL` for the same reason.
    """

    __tablename__ = "planned_meals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    scheduled_for: Mapped[object] = mapped_column(Date, nullable=False)
    meal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("meal_templates.id", ondelete="SET NULL")
    )
    kitchen_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("kitchen_items.id", ondelete="SET NULL")
    )
    portion: Mapped[object | None] = mapped_column(Numeric)

    status: Mapped[PlannedMealStatus] = mapped_column(
        Enum(PlannedMealStatus, name="planned_meal_status"),
        nullable=False,
        default=PlannedMealStatus.planned,
    )
    # The grouped nutrition entry this became, once logged.
    log_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
        UniqueConstraint("user_id", "scheduled_for", "meal_type", name="uq_planned_meals_user_id"),
        CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')",
            name="meal_type_is_a_known_slot",
        ),
        Index("ix_planned_meals_user_id_scheduled_for", "user_id", "scheduled_for"),
    )


class PlannedMealValue(Base):
    """Macros the caller typed in, overruling whatever the source would have given.

    Presence of any row for a planned meal means "these numbers are the answer" — which
    is also how an ad-hoc meal with hand-entered values is stored. Absence means derive
    from the template or leftover, and for an ad-hoc meal means genuinely unknown.
    """

    __tablename__ = "planned_meal_values"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    planned_meal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("planned_meals.id", ondelete="CASCADE"), nullable=False
    )
    trackable_key: Mapped[str] = mapped_column(ForeignKey("trackable_types.key"), nullable=False)
    value: Mapped[object] = mapped_column(Numeric, nullable=False)

    __table_args__ = (
        Index("ix_planned_meal_values_planned_meal_id", "planned_meal_id"),
        UniqueConstraint(
            "planned_meal_id", "trackable_key", name="uq_planned_meal_values_planned_meal_id"
        ),
    )
