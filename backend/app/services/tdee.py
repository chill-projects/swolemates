"""TDEE calculator (#19, resolved) — a direct, pure-function port of
docs/legacy/logic/tdee.ts (Mifflin-St Jeor + activity multiplier + goal-based
calorie/protein targets). `calculate_targets` has no DB access, same shape as the
legacy module; `calculate_and_apply_targets` below is the DB-aware wrapper that
reads the caller's profile + latest logged weight and writes the result via the
existing `set_goals` — a one-time bootstrapping tool, re-runnable on request, never
an auto-recalculating background process.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import ActivityLevel, BiologicalSex, GoalType
from app.services import nutrition as nutrition_service
from app.services import profile as profile_service

WEIGHT_TRACKABLE_KEY = "weight_lbs"


@dataclass
class TdeeInputs:
    sex: BiologicalSex
    age: int
    height_in: float
    weight_lbs: float
    activity_level: ActivityLevel
    goal_type: GoalType


@dataclass
class NutritionTargets:
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    fiber_g: int


ACTIVITY_MULTIPLIERS: dict[ActivityLevel, float] = {
    ActivityLevel.sedentary: 1.2,  # little to no exercise
    ActivityLevel.light: 1.375,  # light exercise 1-3 days/week
    ActivityLevel.moderate: 1.55,  # moderate exercise 3-5 days/week
    ActivityLevel.active: 1.725,  # hard exercise 6-7 days/week
    ActivityLevel.very_active: 1.9,  # very hard exercise + physical job
}

# Deficit/surplus and protein-per-lb-bodyweight by goal. Recomp uses a smaller
# deficit than pure weight loss, with higher protein — the standard approach for
# losing fat while preserving/building muscle at the same time.
GOAL_PARAMS: dict[GoalType, tuple[float, float]] = {
    GoalType.lose_weight: (0.8, 0.8),
    GoalType.recomp: (0.85, 0.9),
    GoalType.gain_muscle: (1.1, 0.8),
    GoalType.maintain: (1.0, 0.7),
}


def calculate_bmr(*, sex: BiologicalSex, age: int, height_in: float, weight_lbs: float) -> float:
    """Imperial-unit form of Mifflin-St Jeor (equivalent to the metric version,
    just avoids converting lbs/inches to kg/cm and back)."""
    base = 4.536 * weight_lbs + 15.88 * height_in - 5 * age
    return base + 5 if sex == BiologicalSex.male else base - 161


def calculate_tdee(inputs: TdeeInputs) -> float:
    bmr = calculate_bmr(
        sex=inputs.sex, age=inputs.age, height_in=inputs.height_in, weight_lbs=inputs.weight_lbs
    )
    return bmr * ACTIVITY_MULTIPLIERS[inputs.activity_level]


def distribute_macros(calories: float, protein_g: float) -> tuple[int, int, int]:
    """Fat/carbs/fiber all scale with total calories; protein is passed in as a
    fixed anchor (based on bodyweight) rather than derived here. Returns
    (carbs_g, fat_g, fiber_g), all rounded grams."""
    fat = (calories * 0.27) / 9  # ~27% of calories from fat
    carbs = max((calories - protein_g * 4 - fat * 9) / 4, 0)
    fiber = (calories / 1000) * 14  # ~14g per 1000 cal, standard guideline
    return round(carbs), round(fat), round(fiber)


def calculate_targets(inputs: TdeeInputs) -> tuple[NutritionTargets, float]:
    """Returns (targets, tdee_estimate)."""
    tdee = calculate_tdee(inputs)
    calorie_multiplier, protein_per_lb = GOAL_PARAMS[inputs.goal_type]

    calories = round(tdee * calorie_multiplier)
    protein = round(inputs.weight_lbs * protein_per_lb)
    carbs, fat, fiber = distribute_macros(calories, protein)

    targets = NutritionTargets(
        calories=calories, protein_g=protein, carbs_g=carbs, fat_g=fat, fiber_g=fiber
    )
    return targets, tdee


async def calculate_and_apply_targets(
    session: AsyncSession, user_sub: str
) -> tuple[NutritionTargets, float]:
    """Raises ValueError naming whatever's missing — an incomplete profile or no
    weight logged yet — rather than guessing. Never touches `is_streak_target`;
    that stays the user's own separate, explicit choice (#6, resolved)."""
    profile = await profile_service.get_or_create_profile(session, user_sub)
    missing = [
        label
        for label, value in [
            ("sex", profile.sex),
            ("age", profile.age),
            ("height", profile.height_in),
            ("activity level", profile.activity_level),
            ("goal type", profile.goal_type),
        ]
        if value is None
    ]
    weight = await nutrition_service.get_latest_trackable_value(
        session, user_sub, WEIGHT_TRACKABLE_KEY
    )
    if weight is None:
        missing.append("a logged weight")
    if missing:
        raise ValueError(
            "Need a bit more info before I can calculate targets: " + ", ".join(missing) + "."
        )

    inputs = TdeeInputs(
        sex=profile.sex,
        age=profile.age,
        height_in=float(profile.height_in),
        weight_lbs=float(weight),
        activity_level=profile.activity_level,
        goal_type=profile.goal_type,
    )
    targets, tdee = calculate_targets(inputs)

    await nutrition_service.set_goals(
        session,
        user_sub,
        goals=[
            {"trackable_key": "calories", "target_value": Decimal(targets.calories)},
            {"trackable_key": "protein_g", "target_value": Decimal(targets.protein_g)},
            {"trackable_key": "carbs_g", "target_value": Decimal(targets.carbs_g)},
            {"trackable_key": "fat_g", "target_value": Decimal(targets.fat_g)},
            {"trackable_key": "fiber_g", "target_value": Decimal(targets.fiber_g)},
        ],
    )
    return targets, tdee
