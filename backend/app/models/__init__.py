"""Every model must be imported here — Alembic autogenerate only sees registered tables."""

from app.models.base import Base, TimestampMixin
from app.models.nutrition import (
    Goal,
    Log,
    LogValue,
    MealTemplate,
    MealTemplateItem,
    MealTemplateItemValue,
    TrackableType,
)
from app.models.partner import InviteStatus, PartnerInvite, PartnerLink
from app.models.profile import UserProfile, WeightUnit
from app.models.workouts import Exercise, SetType, Workout, WorkoutExercise, WorkoutSet, WorkoutType

__all__ = [
    "Base",
    "TimestampMixin",
    "UserProfile",
    "WeightUnit",
    "TrackableType",
    "Log",
    "LogValue",
    "Goal",
    "MealTemplate",
    "MealTemplateItem",
    "MealTemplateItemValue",
    "Exercise",
    "Workout",
    "WorkoutExercise",
    "WorkoutSet",
    "WorkoutType",
    "SetType",
    "PartnerInvite",
    "PartnerLink",
    "InviteStatus",
]
