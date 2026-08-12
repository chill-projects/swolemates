import { type FormEvent, useState } from "react";

import { useCalculateTargets, useCompleteOnboarding, useUpdateProfile } from "../api/profile";

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
        <legend>Stats for calculating targets</legend>
        <p className="muted">
          Used only to estimate a starting point for your calorie/macro targets via the
          "Calculate targets" button below — nothing here is required to use the app.
        </p>
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

      <div className="calculate-targets">
        <button
          type="button"
          onClick={() => calculateTargets.mutate()}
          disabled={calculateTargets.isPending}
        >
          Calculate targets
        </button>
        {calculateTargets.isSuccess && (
          <p className="muted">
            Estimated TDEE: ~{calculateTargets.data.tdee.toLocaleString()} cal/day. Set targets:{" "}
            {calculateTargets.data.calories.toLocaleString()} cal, {calculateTargets.data.protein_g}g
            protein, {calculateTargets.data.carbs_g}g carbs, {calculateTargets.data.fat_g}g fat,{" "}
            {calculateTargets.data.fiber_g}g fiber.
          </p>
        )}
        {calculateTargets.isError && (
          <p className="error">{calculateTargets.error.message}</p>
        )}
      </div>
    </form>
  );
}
