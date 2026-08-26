import { type FormEvent, useEffect, useRef, useState } from "react";

import { type GoalInput, useGoals, useLogWeight, useSetGoals } from "../api/nutrition";
import { useCalculateTargets, useCompleteOnboarding, useUpdateProfile } from "../api/profile";
import { InfoPopover } from "../components/InfoPopover";

// weight_lbs is always stored in pounds regardless of the user's display unit — matches
// app/services/workouts.py's MET-calorie estimate, which reads it back the same way.
const LBS_PER_KG = 2.20462;

const TARGET_KEYS = ["calories", "protein_g", "carbs_g", "fat_g", "fiber_g"] as const;
type TargetKey = (typeof TARGET_KEYS)[number];

/** Direct port of app/services/tdee.py::distribute_macros — fat/carbs/fiber all scale
 *  with total calories; protein is a fixed anchor, not derived here. Only the calorie
 *  field cascades this on edit (matching docs/legacy/components/TargetsForm.tsx). */
function distributeMacros(calories: number, proteinG: number): { carbs: number; fat: number; fiber: number } {
  const fat = (calories * 0.27) / 9;
  const carbs = Math.max((calories - proteinG * 4 - fat * 9) / 4, 0);
  const fiber = (calories / 1000) * 14;
  return { carbs: Math.round(carbs), fat: Math.round(fat), fiber: Math.round(fiber) };
}

type MacroKey = "protein_g" | "carbs_g" | "fat_g";
const CAL_PER_GRAM: Record<MacroKey, number> = { protein_g: 4, carbs_g: 4, fat_g: 9 };

/** Editing protein, carbs, or fat directly (as opposed to calories) keeps the calorie
 *  target fixed and lets the *other two* of those three macros absorb the difference —
 *  split proportionally to their current calorie contribution to each other, not their
 *  gram amounts (fat is more calorie-dense per gram, so a gram-preserving split would
 *  visibly favor it). This mirrors how carbs/fat already move together in a fixed ratio
 *  when calories itself changes (real macro calculators — e.g. Ripped Body's — use the
 *  same "carbs and fat scale together by calories" convention there). Fiber sits outside
 *  this entirely; it doesn't contribute to the calorie total in this app's model. */
function redistributeOtherMacros(
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

type WeightUnit = "lbs" | "kg";
type BiologicalSex = "male" | "female";
type ActivityLevel = "sedentary" | "light" | "moderate" | "active" | "very_active";
type GoalType = "lose_weight" | "maintain" | "gain_muscle" | "recomp";

type ProfileFormProps = {
  profile: {
    weight_unit: WeightUnit;
    coach_notes: string | null;
    sex?: BiologicalSex | null;
    age?: number | null;
    height_in?: string | null;
    activity_level?: ActivityLevel | null;
    goal_type?: GoalType | null;
  };
  /** Welcome-flow use: mark onboarding complete once the save succeeds. */
  completeOnboardingOnSave?: boolean;
  onSaved?: () => void;
};

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

export function ProfileForm({ profile, completeOnboardingOnSave, onSaved }: ProfileFormProps) {
  const [weightUnit, setWeightUnit] = useState<WeightUnit>(profile.weight_unit);
  const [coachNotes, setCoachNotes] = useState(profile.coach_notes ?? "");
  const [sex, setSex] = useState<BiologicalSex | "">(profile.sex ?? "");
  const [age, setAge] = useState(profile.age?.toString() ?? "");
  const totalHeightIn = profile.height_in ? Math.round(Number(profile.height_in)) : null;
  const [heightFt, setHeightFt] = useState(totalHeightIn ? Math.floor(totalHeightIn / 12).toString() : "");
  const [heightIn, setHeightIn] = useState(totalHeightIn ? (totalHeightIn % 12).toString() : "");
  const [activityLevel, setActivityLevel] = useState<ActivityLevel | "">(profile.activity_level ?? "");
  const [goalType, setGoalType] = useState<GoalType | "">(profile.goal_type ?? "");

  const updateProfile = useUpdateProfile();
  const completeOnboarding = useCompleteOnboarding();
  const calculateTargets = useCalculateTargets();

  const [weightInput, setWeightInput] = useState("");
  const logWeight = useLogWeight();

  function handleLogWeight() {
    const value = Number(weightInput);
    if (!value) return;
    const weightLbs = weightUnit === "kg" ? value * LBS_PER_KG : value;
    logWeight.mutate(weightLbs, { onSuccess: () => setWeightInput("") });
  }

  // Editable targets (#TDEE, legacy parity): calculate_targets already persists what it
  // computes, so this is purely for adjusting afterward — "the numbers below are fully
  // editable" per docs/legacy/components/TargetsForm.tsx. Seeded once from whichever
  // comes first, existing goals (a returning visit) or a fresh calculation, then left
  // alone — re-seeding on every goals refetch would clobber in-progress edits.
  const goals = useGoals();
  const setGoals = useSetGoals();
  const [targets, setTargets] = useState<Record<TargetKey, string>>({
    calories: "",
    protein_g: "",
    carbs_g: "",
    fat_g: "",
    fiber_g: "",
  });
  const seededTargets = useRef(false);

  useEffect(() => {
    if (seededTargets.current || !goals.data || goals.data.length === 0) return;
    seededTargets.current = true;
    const byKey = Object.fromEntries(goals.data.map((g) => [g.trackable_key, g.target_value]));
    setTargets((t) => ({
      ...t,
      ...Object.fromEntries(
        TARGET_KEYS.filter((k) => byKey[k] != null).map((k) => [k, String(byKey[k])]),
      ),
    }));
  }, [goals.data]);

  function seedTargetsFromCalculation(data: {
    calories: number;
    protein_g: number;
    carbs_g: number;
    fat_g: number;
    fiber_g: number;
  }) {
    seededTargets.current = true;
    setTargets({
      calories: String(data.calories),
      protein_g: String(data.protein_g),
      carbs_g: String(data.carbs_g),
      fat_g: String(data.fat_g),
      fiber_g: String(data.fiber_g),
    });
  }

  function handleCalorieTargetChange(value: string) {
    const protein = Number(targets.protein_g);
    const calories = Number(value);
    if (value && calories && targets.protein_g && protein) {
      const { carbs, fat, fiber } = distributeMacros(calories, protein);
      setTargets((t) => ({
        ...t,
        calories: value,
        carbs_g: String(carbs),
        fat_g: String(fat),
        fiber_g: String(fiber),
      }));
    } else {
      setTargets((t) => ({ ...t, calories: value }));
    }
  }

  function handleMacroTargetChange(key: MacroKey, value: string) {
    const calories = Number(targets.calories);
    const newValue = Number(value);
    if (!value || !newValue || !targets.calories || !calories) {
      setTargets((t) => ({ ...t, [key]: value }));
      return;
    }
    const current: Record<MacroKey, number> = {
      protein_g: Number(targets.protein_g) || 0,
      carbs_g: Number(targets.carbs_g) || 0,
      fat_g: Number(targets.fat_g) || 0,
    };
    const next = redistributeOtherMacros(key, newValue, current, calories);
    setTargets((t) => ({
      ...t,
      protein_g: String(next.protein_g),
      carbs_g: String(next.carbs_g),
      fat_g: String(next.fat_g),
    }));
  }

  function handleSaveTargets() {
    const body: GoalInput[] = TARGET_KEYS.filter((k) => targets[k] !== "").map((k) => ({
      trackable_key: k,
      target_value: Number(targets[k]),
    }));
    if (body.length === 0) return;
    setGoals.mutate(body);
  }

  const hasTargets = TARGET_KEYS.some((k) => targets[k] !== "");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const combinedHeightIn =
      heightFt !== "" || heightIn !== "" ? (Number(heightFt) || 0) * 12 + (Number(heightIn) || 0) : undefined;
    updateProfile.mutate(
      {
        weight_unit: weightUnit,
        coach_notes: coachNotes,
        sex: sex || undefined,
        age: age ? Number(age) : undefined,
        height_in: combinedHeightIn,
        activity_level: activityLevel || undefined,
        goal_type: goalType || undefined,
      },
      {
        onSuccess: () => {
          if (completeOnboardingOnSave) {
            completeOnboarding.mutate(undefined, { onSuccess: onSaved });
          } else {
            onSaved?.();
          }
        },
      },
    );
  }

  return (
    <form className="profile-form" onSubmit={handleSubmit}>
      <label>
        Weight unit
        <select
          value={weightUnit}
          onChange={(e) => setWeightUnit(e.target.value as WeightUnit)}
        >
          <option value="lbs">lbs</option>
          <option value="kg">kg</option>
        </select>
      </label>
      <label>
        Coach notes
        <textarea
          value={coachNotes}
          onChange={(e) => setCoachNotes(e.target.value)}
          placeholder="e.g. bad left knee, only have dumbbells at home"
        />
      </label>

      <fieldset>
        <legend>
          Stats for calculating targets
          <InfoPopover label="About these stats">
            <p className="info-popover-title">Stats for calculating targets</p>
            <p className="muted">
              Used only to estimate a starting point for your calorie/macro targets via the
              "Calculate targets" button below — nothing here is required to use the app.
            </p>
          </InfoPopover>
        </legend>
        <label>
          Current weight ({weightUnit})
          <input
            type="number"
            inputMode="decimal"
            value={weightInput}
            onChange={(e) => setWeightInput(e.target.value)}
            placeholder={weightUnit === "kg" ? "e.g. 68" : "e.g. 150"}
          />
        </label>
        <div className="calculate-targets">
          <button
            type="button"
            onClick={handleLogWeight}
            disabled={!weightInput || logWeight.isPending}
          >
            Log weight
          </button>
          {logWeight.isSuccess && <p className="muted">Logged.</p>}
          {logWeight.isError && <p className="error">{logWeight.error.message}</p>}
        </div>
        <label>
          Sex
          <select value={sex} onChange={(e) => setSex(e.target.value as BiologicalSex)}>
            <option value="">—</option>
            <option value="female">Female</option>
            <option value="male">Male</option>
          </select>
        </label>
        <label>
          Age
          <input
            type="number"
            inputMode="numeric"
            value={age}
            onChange={(e) => setAge(e.target.value)}
          />
        </label>
        <label>
          Height (ft)
          <input
            type="number"
            inputMode="numeric"
            value={heightFt}
            onChange={(e) => setHeightFt(e.target.value)}
          />
        </label>
        <label>
          Height (in)
          <input
            type="number"
            inputMode="numeric"
            value={heightIn}
            onChange={(e) => setHeightIn(e.target.value)}
          />
        </label>
        <label>
          Activity level
          <select
            value={activityLevel}
            onChange={(e) => setActivityLevel(e.target.value as ActivityLevel)}
          >
            <option value="">—</option>
            {ACTIVITY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Goal
          <select value={goalType} onChange={(e) => setGoalType(e.target.value as GoalType)}>
            <option value="">—</option>
            {GOAL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </fieldset>

      <button type="submit" disabled={updateProfile.isPending}>
        Save
      </button>
      {updateProfile.isSuccess && <p className="muted">Saved.</p>}
      {updateProfile.isError && <p className="error">{updateProfile.error.message}</p>}

      <div className="calculate-targets">
        <button
          type="button"
          onClick={() => calculateTargets.mutate(undefined, { onSuccess: seedTargetsFromCalculation })}
          disabled={calculateTargets.isPending}
        >
          Calculate targets
        </button>
        {calculateTargets.isSuccess && (
          <p className="muted">Estimated TDEE: ~{calculateTargets.data.tdee.toLocaleString()} cal/day.</p>
        )}
        {calculateTargets.isError && (
          <p className="error">{calculateTargets.error.message}</p>
        )}
      </div>

      {hasTargets && (
        <fieldset>
          <legend>
            Daily targets
            <InfoPopover label="How editing these targets works">
              <p className="info-popover-title">Daily targets</p>
              <p className="muted">
                Adjusting calories redistributes fat/carbs/fiber around it, protein fixed to
                your bodyweight. Adjusting protein, carbs, or fat instead keeps calories fixed
                and splits the difference between the other two, proportionally to their
                current split.
              </p>
            </InfoPopover>
          </legend>
          <label>
            Calories
            <input
              type="number"
              inputMode="numeric"
              value={targets.calories}
              onChange={(e) => handleCalorieTargetChange(e.target.value)}
            />
          </label>
          <label>
            Protein (g)
            <input
              type="number"
              inputMode="numeric"
              value={targets.protein_g}
              onChange={(e) => handleMacroTargetChange("protein_g", e.target.value)}
            />
          </label>
          <label>
            Carbs (g)
            <input
              type="number"
              inputMode="numeric"
              value={targets.carbs_g}
              onChange={(e) => handleMacroTargetChange("carbs_g", e.target.value)}
            />
          </label>
          <label>
            Fat (g)
            <input
              type="number"
              inputMode="numeric"
              value={targets.fat_g}
              onChange={(e) => handleMacroTargetChange("fat_g", e.target.value)}
            />
          </label>
          <label>
            Fiber (g)
            <input
              type="number"
              inputMode="numeric"
              value={targets.fiber_g}
              onChange={(e) => setTargets((t) => ({ ...t, fiber_g: e.target.value }))}
            />
          </label>
          <button type="button" onClick={handleSaveTargets} disabled={setGoals.isPending}>
            Save targets
          </button>
          {setGoals.isSuccess && <p className="muted">Saved.</p>}
          {setGoals.isError && <p className="error">{setGoals.error.message}</p>}
        </fieldset>
      )}
    </form>
  );
}
