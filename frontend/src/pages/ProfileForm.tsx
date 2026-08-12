import { type FormEvent, useState } from "react";

import { useCompleteOnboarding, useUpdateProfile } from "../api/profile";

type WeightUnit = "lbs" | "kg";

type ProfileFormProps = {
  profile: { weight_unit: WeightUnit; coach_notes: string | null };
  /** Welcome-flow use: mark onboarding complete once the save succeeds. */
  completeOnboardingOnSave?: boolean;
  onSaved?: () => void;
};

export function ProfileForm({ profile, completeOnboardingOnSave, onSaved }: ProfileFormProps) {
  const [weightUnit, setWeightUnit] = useState<WeightUnit>(profile.weight_unit);
  const [coachNotes, setCoachNotes] = useState(profile.coach_notes ?? "");
  const updateProfile = useUpdateProfile();
  const completeOnboarding = useCompleteOnboarding();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    updateProfile.mutate(
      { weight_unit: weightUnit, coach_notes: coachNotes },
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
      <button type="submit" disabled={updateProfile.isPending}>
        Save
      </button>
    </form>
  );
}
