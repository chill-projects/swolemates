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
from app.models.profile import UserProfile, WeightUnit
from app.models.tmpx import TmpxItem

__all__ = [
    "Base",
    "TimestampMixin",
    "TmpxItem",
    "UserProfile",
    "WeightUnit",
    "TrackableType",
    "Log",
    "LogValue",
    "Goal",
    "MealTemplate",
    "MealTemplateItem",
    "MealTemplateItemValue",
]
