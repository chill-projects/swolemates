import { type FormEvent, useEffect, useRef, useState } from "react";

import { type GoalInput, useGoals, useLogWeight, useSetGoals } from "../api/nutrition";
import { useCalculateTargets, useCompleteOnboarding, useUpdateProfile } from "../api/profile";
import { InfoPopover } from "../components/InfoPopover";
import { detectedTimezone } from "../lib/datetime";
import {
  ACTIVITY_OPTIONS,
  GOAL_OPTIONS,
  LBS_PER_KG,
  TARGET_KEYS,
  type ActivityLevel,
  type BiologicalSex,
  type GoalType,
  type MacroKey,
  type TargetKey,
  type WeightUnit,
  distributeMacros,
  redistributeOtherMacros,
  timezoneOptions,
} from "./profileTargets";

type ProfileFormProps = {
  profile: {
    weight_unit: WeightUnit;
    coach_notes: string | null;
    timezone?: string | null;
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

export function ProfileForm({ profile, completeOnboardingOnSave, onSaved }: ProfileFormProps) {
  const [weightUnit, setWeightUnit] = useState<WeightUnit>(profile.weight_unit);
  const [coachNotes, setCoachNotes] = useState(profile.coach_notes ?? "");
  const detectedTz = detectedTimezone();
  const [timezone, setTimezone] = useState(profile.timezone ?? detectedTz);
  const tzOptions = timezoneOptions(timezone);
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
        timezone,
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
        Timezone
        <select value={timezone} onChange={(e) => setTimezone(e.target.value)}>
          {tzOptions.map((z) => (
            <option key={z} value={z}>
              {z}
            </option>
          ))}
        </select>
        <span className="muted">
          {timezone === detectedTz
            ? "Detected from your browser. Used for streaks and which day meals and workouts fall on."
            : `Overriding your browser's ${detectedTz}.`}
        </span>
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
        <div style={{ display: "flex", gap: "0.75rem", width: "100%" }}>
          <label style={{ flex: 1 }}>
            Height (ft)
            <input
              type="number"
              inputMode="numeric"
              value={heightFt}
              onChange={(e) => setHeightFt(e.target.value)}
            />
          </label>
          <label style={{ flex: 1 }}>
            Height (in)
            <input
              type="number"
              inputMode="numeric"
              value={heightIn}
              onChange={(e) => setHeightIn(e.target.value)}
            />
          </label>
        </div>
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
