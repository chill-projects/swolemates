import enum

from sqlalchemy import DateTime, Enum, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class WeightUnit(enum.StrEnum):
    lbs = "lbs"
    kg = "kg"


class BiologicalSex(enum.StrEnum):
    male = "male"
    female = "female"


class ActivityLevel(enum.StrEnum):
    sedentary = "sedentary"
    light = "light"
    moderate = "moderate"
    active = "active"
    very_active = "very_active"


class GoalType(enum.StrEnum):
    lose_weight = "lose_weight"
    maintain = "maintain"
    gain_muscle = "gain_muscle"
    recomp = "recomp"


class UserProfile(Base, TimestampMixin):
    """One row per user, keyed by the WorkOS `sub` — same `user_id str`, no-FK
    convention as everywhere else. Holds whatever doesn't fit a feature-specific
    table: display preferences, freeform coaching context, onboarding state, and
    the TDEE calculator's inputs.

    `weight_unit` is display-only — every stored weight value is canonical lbs
    (see workouts-v1.md §2); this just controls conversion at render time.
    `coach_notes` is read by the `coach` prompt alongside `get_goals`/`get_progress`.
    `onboarding_completed_at` is set once, so the welcome step never re-shows.
    `sex`/`age`/`height_in`/`activity_level`/`goal_type` feed the Mifflin-St Jeor
    calculator (#19, resolved) — all nullable, since the calculator is opt-in and
    re-runnable, not a hard onboarding gate. Current weight is *not* stored here —
    it's the most recent `weight_lbs` trackable log, per #19's resolution.

    `display_name` (#5, added for Partner v1) is a cache, not the source of truth —
    WorkOS claims (`first_name`/`last_name`) are per-request JWT contents, never
    persisted anywhere else, so there'd otherwise be no way to show *another* user's
    name (e.g. a linked partner's) without a live WorkOS Management API call. Kept
    fresh opportunistically by `whoami`, which every authenticated SPA session calls
    on load — by the time any partner action is reachable, this is guaranteed set.
    """

    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    # IANA timezone name (e.g. "America/Los_Angeles"). Nullable: unset ⇒ UTC day
    # boundaries, same as before this column existed. Seeded from the browser's
    # `X-Timezone` on first `whoami`, overridable from Settings; the MCP/chat path
    # has no live zone and reads this. See `services/timezones.py`.
    timezone: Mapped[str | None] = mapped_column(String(64))
    weight_unit: Mapped[WeightUnit] = mapped_column(
        Enum(WeightUnit, name="weight_unit"), nullable=False, default=WeightUnit.lbs
    )
    coach_notes: Mapped[str | None] = mapped_column(Text)
    onboarding_completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    sex: Mapped[BiologicalSex | None] = mapped_column(Enum(BiologicalSex, name="biological_sex"))
    age: Mapped[int | None] = mapped_column(Integer)
    height_in: Mapped[object | None] = mapped_column(Numeric)
    activity_level: Mapped[ActivityLevel | None] = mapped_column(
        Enum(ActivityLevel, name="activity_level")
    )
    goal_type: Mapped[GoalType | None] = mapped_column(Enum(GoalType, name="nutrition_goal_type"))
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
