"""Nutrition service — split by concern (architecture review, 2026-08-14):
trackables (the trackable-type catalog), goals, meal templates, logs (single-entry
logging + chat-side corrections), and day (the day-vs-goals aggregate view — the only
submodule that depends on the other three).

Re-exported flat here so every existing call site keeps working unchanged:
`from app.services import nutrition as service; service.log_nutrition(...)`.
"""

from app.services.errors import NotFoundError
from app.services.nutrition.day import (
    DayLog,
    DayLogItem,
    NutritionCalendarDay,
    NutritionDay,
    TrackableProgress,
    get_nutrition_calendar,
    get_nutrition_day,
    get_nutrition_streak,
)
from app.services.nutrition.goals import get_goals, set_goals
from app.services.nutrition.logs import (
    amend_last_log,
    get_latest_trackable_value,
    get_log_values,
    log_nutrition,
    update_nutrition_log,
)
from app.services.nutrition.templates import (
    MealTemplateItemOut,
    MealTemplateSummary,
    delete_meal_template,
    list_meal_templates,
    log_meal_template,
    save_meal_template,
    update_meal_template_item,
)
from app.services.nutrition.trackables import list_trackable_types

__all__ = [
    "NotFoundError",
    "TrackableProgress",
    "DayLogItem",
    "DayLog",
    "MealTemplateItemOut",
    "MealTemplateSummary",
    "NutritionDay",
    "NutritionCalendarDay",
    "get_nutrition_calendar",
    "list_trackable_types",
    "log_nutrition",
    "get_log_values",
    "get_latest_trackable_value",
    "update_nutrition_log",
    "amend_last_log",
    "get_goals",
    "set_goals",
    "list_meal_templates",
    "save_meal_template",
    "update_meal_template_item",
    "delete_meal_template",
    "log_meal_template",
    "get_nutrition_day",
    "get_nutrition_streak",
]
