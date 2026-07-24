"use client";

import { useState } from "react";
import { saveActivity } from "./actions";
import type { Database } from "@/lib/supabase/database.types";

type ActivityType = Database["public"]["Enums"]["activity_type"];

const ACTIVITY_TYPES: { value: ActivityType; label: string }[] = [
  { value: "yoga", label: "Yoga" },
  { value: "pilates", label: "Pilates" },
  { value: "cardio", label: "Cardio" },
  { value: "other", label: "Other" },
];

export function ActivityForm() {
  const [title, setTitle] = useState("");
  const [activityType, setActivityType] = useState<ActivityType>("yoga");
  const [durationMinutes, setDurationMinutes] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setError(null);

    if (durationMinutes === "" || Number(durationMinutes) <= 0) {
      setError("Enter a duration in minutes.");
      return;
    }

    setSaving(true);
    try {
      await saveActivity({
        title,
        activityType,
        durationMinutes: Number(durationMinutes),
        notes,
      });
    } catch (err) {
      setSaving(false);
      setError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Title (optional, e.g. 'Yoga with Adriene')"
        className="rounded-xl border border-line bg-card px-3 py-2"
      />

      {error && (
        <p className="rounded-xl bg-coral-pale px-3 py-2 text-sm text-red">
          {error}
        </p>
      )}

      <label className="flex flex-col gap-1 text-sm">
        <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
          Type
        </span>
        <select
          value={activityType}
          onChange={(e) => setActivityType(e.target.value as ActivityType)}
          className="rounded-xl border border-line bg-card px-3 py-2"
        >
          {ACTIVITY_TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-sm">
        <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
          Duration (minutes)
        </span>
        <input
          type="number"
          inputMode="numeric"
          value={durationMinutes}
          onChange={(e) => setDurationMinutes(e.target.value)}
          className="rounded-xl border border-line bg-card px-3 py-2"
        />
      </label>

      <label className="flex flex-col gap-1 text-sm">
        <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
          Notes (optional)
        </span>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          className="rounded-xl border border-line bg-card px-3 py-2"
        />
      </label>

      <button
        type="button"
        onClick={handleSave}
        disabled={saving}
        className="rounded-full bg-teal px-4 py-2.5 font-medium text-white disabled:opacity-50"
      >
        {saving ? "Saving…" : "Save activity"}
      </button>
    </div>
  );
}
