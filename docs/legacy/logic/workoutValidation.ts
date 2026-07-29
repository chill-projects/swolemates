export type ValidationSetRow = {
  setType: "reps" | "time";
  actualWeight: string;
  actualReps: string;
  workSeconds: string;
};

export type ValidationEntry = {
  exerciseName: string;
  sets: ValidationSetRow[];
};

export function validateWorkout(entries: ValidationEntry[]): string | null {
  if (entries.length === 0) {
    return "Add at least one exercise.";
  }

  for (const entry of entries) {
    if (entry.sets.length === 0) {
      return `${entry.exerciseName} needs at least one set.`;
    }
    for (const set of entry.sets) {
      if (set.setType === "reps") {
        if (set.actualReps === "" || Number(set.actualReps) <= 0) {
          return `${entry.exerciseName}: every rep set needs reps > 0.`;
        }
        if (set.actualWeight === "" || Number(set.actualWeight) < 0) {
          return `${entry.exerciseName}: every rep set needs a weight (0 is fine for bodyweight).`;
        }
      } else {
        if (set.workSeconds === "" || Number(set.workSeconds) <= 0) {
          return `${entry.exerciseName}: every timed set needs work seconds > 0.`;
        }
      }
    }
  }

  return null;
}
