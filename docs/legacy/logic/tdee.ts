export type BiologicalSex = "male" | "female";
export type ActivityLevel = "sedentary" | "light" | "moderate" | "active" | "very_active";
export type GoalType = "lose_weight" | "maintain" | "gain_muscle" | "recomp";

export type TdeeInputs = {
  sex: BiologicalSex;
  age: number;
  heightIn: number;
  weightLbs: number;
  activityLevel: ActivityLevel;
  goalType: GoalType;
};

export type NutritionTargets = {
  calories: number;
  protein: number;
  carbs: number;
  fat: number;
  fiber: number;
};

export type DayTotals = {
  calories: number;
  protein: number;
  carbs: number;
  fat: number;
  fiber: number;
};

// Imperial-unit form of Mifflin-St Jeor (equivalent to the metric version,
// just avoids converting lbs/inches to kg/cm and back).
export function calculateBMR({ sex, age, heightIn, weightLbs }: Pick<TdeeInputs, "sex" | "age" | "heightIn" | "weightLbs">): number {
  const base = 4.536 * weightLbs + 15.88 * heightIn - 5 * age;
  return sex === "male" ? base + 5 : base - 161;
}

const ACTIVITY_MULTIPLIERS: Record<ActivityLevel, number> = {
  sedentary: 1.2, // little to no exercise
  light: 1.375, // light exercise 1-3 days/week
  moderate: 1.55, // moderate exercise 3-5 days/week
  active: 1.725, // hard exercise 6-7 days/week
  very_active: 1.9, // very hard exercise + physical job
};

export function calculateTDEE(inputs: TdeeInputs): number {
  return calculateBMR(inputs) * ACTIVITY_MULTIPLIERS[inputs.activityLevel];
}

// Deficit/surplus and protein-per-lb-bodyweight by goal. Recomp uses a
// smaller deficit than pure weight loss, with higher protein — the standard
// approach for losing fat while preserving/building muscle at the same time.
const GOAL_PARAMS: Record<GoalType, { calorieMultiplier: number; proteinPerLb: number }> = {
  lose_weight: { calorieMultiplier: 0.8, proteinPerLb: 0.8 },
  recomp: { calorieMultiplier: 0.85, proteinPerLb: 0.9 },
  gain_muscle: { calorieMultiplier: 1.1, proteinPerLb: 0.8 },
  maintain: { calorieMultiplier: 1.0, proteinPerLb: 0.7 },
};

// Fat/carbs/fiber all scale with total calories; protein is passed in as a
// fixed anchor (based on bodyweight) rather than derived here, so this can
// be reused whenever calories change without needing to re-run the full
// TDEE calculation or know bodyweight again.
export function distributeMacros(
  calories: number,
  proteinG: number,
): Omit<NutritionTargets, "calories" | "protein"> {
  const fat = (calories * 0.27) / 9; // ~27% of calories from fat
  const carbs = Math.max((calories - proteinG * 4 - fat * 9) / 4, 0);
  const fiber = (calories / 1000) * 14; // ~14g per 1000 cal, standard guideline

  return {
    carbs: Math.round(carbs),
    fat: Math.round(fat),
    fiber: Math.round(fiber),
  };
}

export function calculateTargets(inputs: TdeeInputs): NutritionTargets {
  const tdee = calculateTDEE(inputs);
  const { calorieMultiplier, proteinPerLb } = GOAL_PARAMS[inputs.goalType];

  const calories = Math.round(tdee * calorieMultiplier);
  const protein = Math.round(inputs.weightLbs * proteinPerLb);
  const { carbs, fat, fiber } = distributeMacros(calories, protein);

  return { calories, protein, carbs, fat, fiber };
}

// Derived from GOAL_PARAMS' calorieMultiplier rather than re-encoded per
// goal — a goal below TDEE is a deficit, above is a surplus, at TDEE is
// maintenance. This is the single source of truth for which direction
// "hitting the goal" means; nothing downstream re-decides it per GoalType.
type GoalDirection = "deficit" | "surplus" | "maintain";

function goalDirection(goalType: GoalType): GoalDirection {
  const { calorieMultiplier } = GOAL_PARAMS[goalType];
  if (calorieMultiplier < 1) return "deficit";
  if (calorieMultiplier > 1) return "surplus";
  return "maintain";
}

export function remainingOf(value: number, target: number): number {
  return Math.max(Math.round(target - value), 0);
}

export function macroPercent(value: number, target: number | undefined): number {
  return target ? Math.min((value / target) * 100, 100) : 0;
}

// A small grace window absorbs normal estimation noise (especially from
// photo-based logging) without being pedantic about it. Protein isn't a
// factor here — this is calorie-direction only.
export function dayStatus(
  totals: DayTotals | undefined,
  targets: NutritionTargets | null,
  goalType: GoalType | null,
): "hit" | "miss" | "no-data" {
  if (!totals) return "no-data";
  if (!targets) return "hit"; // no targets set yet — just show logged vs not
  if (!goalType) {
    return totals.calories >= targets.calories * 0.9 &&
      totals.calories <= targets.calories * 1.1
      ? "hit"
      : "miss";
  }

  switch (goalDirection(goalType)) {
    case "deficit":
      return totals.calories <= targets.calories * 1.05 ? "hit" : "miss";
    case "surplus":
      return totals.calories >= targets.calories * 0.95 ? "hit" : "miss";
    case "maintain":
      return totals.calories >= targets.calories * 0.9 &&
        totals.calories <= targets.calories * 1.1
        ? "hit"
        : "miss";
  }
}

export function dateKeyFromDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function dateKeyFromParts(year: number, month: number, day: number): string {
  return dateKeyFromDate(new Date(year, month, day));
}

export function computeStreak(loggedDateKeys: Set<string>): number {
  const today = new Date();
  const cursor = new Date(today.getFullYear(), today.getMonth(), today.getDate());

  // If nothing logged today yet, the streak can still be "current" as long
  // as yesterday was logged — start counting from there instead.
  const todayKey = dateKeyFromDate(cursor);
  if (!loggedDateKeys.has(todayKey)) {
    cursor.setDate(cursor.getDate() - 1);
  }

  let streak = 0;
  while (loggedDateKeys.has(dateKeyFromDate(cursor))) {
    streak += 1;
    cursor.setDate(cursor.getDate() - 1);
  }
  return streak;
}
