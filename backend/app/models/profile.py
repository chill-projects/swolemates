import enum

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class WeightUnit(enum.StrEnum):
    lbs = "lbs"
    kg = "kg"


class UserProfile(Base, TimestampMixin):
    """One row per user, keyed by the WorkOS `sub` — same `user_id str`, no-FK
    convention as everywhere else. Holds whatever doesn't fit a feature-specific
    table: display preferences, freeform coaching context, and onboarding state.

    `weight_unit` is display-only — every stored weight value is canonical lbs
    (see workouts-v1.md §2); this just controls conversion at render time.
    `coach_notes` is read by the `coach` prompt alongside `get_goals`/`get_progress`.
    `onboarding_completed_at` is set once, so the welcome step never re-shows.
    """

    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    weight_unit: Mapped[WeightUnit] = mapped_column(
        Enum(WeightUnit, name="weight_unit"), nullable=False, default=WeightUnit.lbs
    )
    coach_notes: Mapped[str | None] = mapped_column(Text)
    onboarding_completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
