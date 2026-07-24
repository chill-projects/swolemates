"use client";

import { useState } from "react";
import { saveTargets } from "./actions";
import {
  calculateTargets,
  calculateTDEE,
  distributeMacros,
  type BiologicalSex,
  type ActivityLevel,
  type GoalType,
} from "@/lib/tdee";
import type { Database } from "@/lib/supabase/database.types";

type Profile = Pick<
  Database["public"]["Tables"]["profiles"]["Row"],
  | "sex"
  | "age"
  | "height_in"
  | "weight_lbs"
  | "activity_level"
  | "goal_type"
  | "calorie_target"
  | "protein_target"
  | "carb_target"
  | "fat_target"
  | "fiber_target"
>;

const ACTIVITY_OPTIONS: { value: ActivityLevel; label: string }[] = [
  { value: "sedentary", label: "Sedentary (little to no exercise)" },
  { value: "light", label: "Light (1-3 days/week)" },
  { value: "moderate", label: "Moderate (3-5 days/week)" },
  { value: "active", label: "Active (6-7 days/week)" },
  { value: "very_active", label: "Very active (hard exercise + physical job)" },
];

const GOAL_OPTIONS: { value: GoalType; label: string }[] = [
  { value: "lose_weight", label: "Lose weight" },
  { value: "recomp", label: "Lose fat, keep/build muscle (recomposition)" },
  { value: "gain_muscle", label: "Gain muscle" },
  { value: "maintain", label: "Maintain" },
];

export function TargetsForm({ profile }: { profile: Profile | null }) {
  const [sex, setSex] = useState<BiologicalSex | "">(profile?.sex ?? "");
  const [age, setAge] = useState(profile?.age?.toString() ?? "");
  const [heightFt, setHeightFt] = useState(
    profile?.height_in ? Math.floor(profile.height_in / 12).toString() : "",
  );
  const [heightIn, setHeightIn] = useState(
    profile?.height_in ? Math.round(profile.height_in % 12).toString() : "",
  );
  const [weightLbs, setWeightLbs] = useState(profile?.weight_lbs?.toString() ?? "");
  const [activityLevel, setActivityLevel] = useState<ActivityLevel | "">(
    profile?.activity_level ?? "",
  );
  const [goalType, setGoalType] = useState<GoalType | "">(profile?.goal_type ?? "");

  const [calorieTarget, setCalorieTarget] = useState(profile?.calorie_target?.toString() ?? "");
  const [proteinTarget, setProteinTarget] = useState(profile?.protein_target?.toString() ?? "");
  const [carbTarget, setCarbTarget] = useState(profile?.carb_target?.toString() ?? "");
  const [fatTarget, setFatTarget] = useState(profile?.fat_target?.toString() ?? "");
  const [fiberTarget, setFiberTarget] = useState(profile?.fiber_target?.toString() ?? "");

  const [tdeePreview, setTdeePreview] = useState<number | null>(null);
  const [calcError, setCalcError] = useState<string | null>(null);

  const totalHeightIn =
    heightFt !== "" || heightIn !== ""
      ? (Number(heightFt) || 0) * 12 + (Number(heightIn) || 0)
      : null;

  // Protein stays anchored to bodyweight — adjusting calories redistributes
  // fat/carbs/fiber around it instead of scaling protein too.
  function handleCalorieChange(value: string) {
    setCalorieTarget(value);

    const calories = Number(value);
    const protein = Number(proteinTarget);
    if (!value || !calories || !proteinTarget || !protein) return;

    const { carbs, fat, fiber } = distributeMacros(calories, protein);
    setCarbTarget(carbs.toString());
    setFatTarget(fat.toString());
    setFiberTarget(fiber.toString());
  }

  function handleCalculate() {
    setCalcError(null);

    if (!sex || !age || !totalHeightIn || !weightLbs || !activityLevel || !goalType) {
      setCalcError(
        "Fill in sex, age, height, weight, activity level, and goal to calculate.",
      );
      return;
    }

    const inputs = {
      sex,
      age: Number(age),
      heightIn: totalHeightIn,
      weightLbs: Number(weightLbs),
      activityLevel,
      goalType,
    };

    const targets = calculateTargets(inputs);
    setTdeePreview(Math.round(calculateTDEE(inputs)));
    setCalorieTarget(targets.calories.toString());
    setProteinTarget(targets.protein.toString());
    setCarbTarget(targets.carbs.toString());
    setFatTarget(targets.fat.toString());
    setFiberTarget(targets.fiber.toString());
  }

  return (
    <form action={saveTargets} className="flex flex-col gap-5">
      <div className="flex flex-col gap-3">
        <h2 className="font-display text-lg font-semibold">
          Calculate from your stats
        </h2>
        <p className="text-sm text-ink-soft">
          Uses the Mifflin-St Jeor formula for your estimated TDEE, then
          adjusts calories and protein based on your goal. It&apos;s a solid
          starting point — the numbers below are fully editable afterward.
        </p>

        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
              Sex
            </span>
            <select
              name="sex"
              value={sex}
              onChange={(e) => setSex(e.target.value as BiologicalSex)}
              className="rounded-xl border border-line bg-card px-3 py-2"
            >
              <option value="">—</option>
              <option value="female">Female</option>
              <option value="male">Male</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
              Age
            </span>
            <input
              name="age"
              type="number"
              inputMode="numeric"
              value={age}
              onChange={(e) => setAge(e.target.value)}
              className="rounded-xl border border-line bg-card px-3 py-2"
            />
          </label>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
              Height (ft)
            </span>
            <input
              type="number"
              inputMode="numeric"
              value={heightFt}
              onChange={(e) => setHeightFt(e.target.value)}
              className="rounded-xl border border-line bg-card px-3 py-2"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
              (in)
            </span>
            <input
              type="number"
              inputMode="numeric"
              value={heightIn}
              onChange={(e) => setHeightIn(e.target.value)}
              className="rounded-xl border border-line bg-card px-3 py-2"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
              Weight (lbs)
            </span>
            <input
              name="weightLbs"
              type="number"
              inputMode="decimal"
              value={weightLbs}
              onChange={(e) => setWeightLbs(e.target.value)}
              className="rounded-xl border border-line bg-card px-3 py-2"
            />
          </label>
        </div>
        {/* Hidden field so the combined total height is what gets submitted */}
        <input type="hidden" name="heightIn" value={totalHeightIn ?? ""} />

        <label className="flex flex-col gap-1 text-sm">
          <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
            Activity level
          </span>
          <select
            name="activityLevel"
            value={activityLevel}
            onChange={(e) => setActivityLevel(e.target.value as ActivityLevel)}
            className="rounded-xl border border-line bg-card px-3 py-2"
          >
            <option value="">—</option>
            {ACTIVITY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
            Goal
          </span>
          <select
            name="goalType"
            value={goalType}
            onChange={(e) => setGoalType(e.target.value as GoalType)}
            className="rounded-xl border border-line bg-card px-3 py-2"
          >
            <option value="">—</option>
            {GOAL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>

        {calcError && (
          <p className="rounded-xl bg-coral-pale px-3 py-2 text-sm text-red">
            {calcError}
          </p>
        )}

        <button
          type="button"
          onClick={handleCalculate}
          className="rounded-full border border-teal px-4 py-2 font-medium text-teal"
        >
          Calculate targets
        </button>

        {tdeePreview !== null && (
          <p className="font-mono text-xs text-ink-soft">
            Estimated TDEE: ~{tdeePreview} cal/day
          </p>
        )}
      </div>

      <div className="flex flex-col gap-3 border-t border-line pt-4">
        <h2 className="font-display text-lg font-semibold">Daily targets</h2>
        <p className="-mt-2 text-xs text-ink-soft">
          Adjusting calories redistributes fat/carbs/fiber around it; protein
          stays fixed to your bodyweight.
        </p>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
            Calories
          </span>
          <input
            name="calorieTarget"
            type="number"
            inputMode="numeric"
            value={calorieTarget}
            onChange={(e) => handleCalorieChange(e.target.value)}
            className="rounded-xl border border-line bg-card px-3 py-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
            Protein (g)
          </span>
          <input
            name="proteinTarget"
            type="number"
            inputMode="numeric"
            value={proteinTarget}
            onChange={(e) => setProteinTarget(e.target.value)}
            className="rounded-xl border border-line bg-card px-3 py-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
            Carbs (g)
          </span>
          <input
            name="carbTarget"
            type="number"
            inputMode="numeric"
            value={carbTarget}
            onChange={(e) => setCarbTarget(e.target.value)}
            className="rounded-xl border border-line bg-card px-3 py-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
            Fat (g)
          </span>
          <input
            name="fatTarget"
            type="number"
            inputMode="numeric"
            value={fatTarget}
            onChange={(e) => setFatTarget(e.target.value)}
            className="rounded-xl border border-line bg-card px-3 py-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
            Fiber (g)
          </span>
          <input
            name="fiberTarget"
            type="number"
            inputMode="numeric"
            value={fiberTarget}
            onChange={(e) => setFiberTarget(e.target.value)}
            className="rounded-xl border border-line bg-card px-3 py-2"
          />
        </label>
      </div>

      <button
        type="submit"
        className="rounded-full bg-teal px-4 py-2.5 font-medium text-white"
      >
        Save targets
      </button>
    </form>
  );
}
