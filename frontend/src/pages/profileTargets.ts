/**
 * The target arithmetic and profile option lists, shared by the Profile page and the
 * onboarding form. Extracted when Profile got its own layout (6a) so the two screens
 * can't drift apart on how a macro edit redistributes — this is the app's only copy.
 */

// weight_lbs is always stored in pounds regardless of the user's display unit — matches
// app/services/workouts.py's MET-calorie estimate, which reads it back the same way.
export const LBS_PER_KG = 2.20462;

export const TARGET_KEYS = ["calories", "protein_g", "carbs_g", "fat_g", "fiber_g"] as const;
export type TargetKey = (typeof TARGET_KEYS)[number];

export type WeightUnit = "lbs" | "kg";
export type BiologicalSex = "male" | "female";
export type ActivityLevel = "sedentary" | "light" | "moderate" | "active" | "very_active";
export type GoalType = "lose_weight" | "maintain" | "gain_muscle" | "recomp";
export type MacroKey = "protein_g" | "carbs_g" | "fat_g";

export const ACTIVITY_OPTIONS: { value: ActivityLevel; label: string }[] = [
  { value: "sedentary", label: "Sedentary (little to no exercise)" },
  { value: "light", label: "Light (1-3 days/week)" },
  { value: "moderate", label: "Moderate (3-5 days/week)" },
  { value: "active", label: "Active (6-7 days/week)" },
  { value: "very_active", label: "Very active (hard exercise + physical job)" },
];

export const GOAL_OPTIONS: { value: GoalType; label: string }[] = [
  { value: "lose_weight", label: "Lose weight" },
  { value: "recomp", label: "Lose fat, keep muscle" },
  { value: "gain_muscle", label: "Gain muscle" },
  { value: "maintain", label: "Maintain" },
];

/** Direct port of app/services/tdee.py::distribute_macros — fat/carbs/fiber all scale
 *  with total calories; protein is a fixed anchor, not derived here. Only the calorie
 *  field cascades this on edit (matching docs/legacy/components/TargetsForm.tsx). */
export function distributeMacros(
  calories: number,
  proteinG: number,
): { carbs: number; fat: number; fiber: number } {
  const fat = (calories * 0.27) / 9;
  const carbs = Math.max((calories - proteinG * 4 - fat * 9) / 4, 0);
  const fiber = (calories / 1000) * 14;
  return { carbs: Math.round(carbs), fat: Math.round(fat), fiber: Math.round(fiber) };
}

const CAL_PER_GRAM: Record<MacroKey, number> = { protein_g: 4, carbs_g: 4, fat_g: 9 };

/** Editing protein, carbs, or fat directly (as opposed to calories) keeps the calorie
 *  target fixed and lets the *other two* of those three macros absorb the difference —
 *  split proportionally to their current calorie contribution to each other, not their
 *  gram amounts (fat is more calorie-dense per gram, so a gram-preserving split would
 *  visibly favor it). This mirrors how carbs/fat already move together in a fixed ratio
 *  when calories itself changes (real macro calculators — e.g. Ripped Body's — use the
 *  same "carbs and fat scale together by calories" convention there). Fiber sits outside
 *  this entirely; it doesn't contribute to the calorie total in this app's model. */
export function redistributeOtherMacros(
  edited: MacroKey,
  newValue: number,
  current: Record<MacroKey, number>,
  calories: number,
): Record<MacroKey, number> {
  const [a, b] = (["protein_g", "carbs_g", "fat_g"] as const).filter((k) => k !== edited) as [
    MacroKey,
    MacroKey,
  ];
  const remaining = Math.max(calories - newValue * CAL_PER_GRAM[edited], 0);

  const aCalories = current[a] * CAL_PER_GRAM[a];
  const bCalories = current[b] * CAL_PER_GRAM[b];
  const totalCalories = aCalories + bCalories;
  const aShare = totalCalories > 0 ? aCalories / totalCalories : 0.5;

  return {
    ...current,
    [edited]: newValue,
    [a]: Math.round((remaining * aShare) / CAL_PER_GRAM[a]),
    [b]: Math.round((remaining * (1 - aShare)) / CAL_PER_GRAM[b]),
  };
}

/** Every IANA zone the runtime knows, with UTC and the current value guaranteed
 *  present so the `<select>` can always render its value. */
export function timezoneOptions(current: string): string[] {
  let zones: string[] = [];
  try {
    const supported = (Intl as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf;
    if (supported) zones = supported("timeZone");
  } catch {
    zones = [];
  }
  return [...new Set(["UTC", current, ...zones])];
}
