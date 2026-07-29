"use client";

import { useState } from "react";
import { WorkoutBuilder } from "./WorkoutBuilder";
import { ActivityForm } from "./ActivityForm";

type ExerciseOption = {
  id: string;
  name: string;
  muscle_group: string;
};

export function NewWorkoutClient({
  exercises,
}: {
  exercises: ExerciseOption[];
}) {
  const [mode, setMode] = useState<"strength" | "activity">("strength");

  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4 px-4 py-8">
      <h1 className="font-display text-2xl font-semibold">Log a workout</h1>

      <div className="flex gap-2 rounded-full bg-teal-pale p-1">
        <button
          type="button"
          onClick={() => setMode("strength")}
          className={`flex-1 rounded-full py-2 font-mono text-xs tracking-wide uppercase transition-colors ${
            mode === "strength" ? "bg-teal text-white" : "text-teal"
          }`}
        >
          Strength
        </button>
        <button
          type="button"
          onClick={() => setMode("activity")}
          className={`flex-1 rounded-full py-2 font-mono text-xs tracking-wide uppercase transition-colors ${
            mode === "activity" ? "bg-teal text-white" : "text-teal"
          }`}
        >
          Activity
        </button>
      </div>

      {mode === "strength" ? (
        <WorkoutBuilder exercises={exercises} />
      ) : (
        <ActivityForm />
      )}
    </div>
  );
}
