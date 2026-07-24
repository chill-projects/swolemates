"use client";

import { useMemo, useState } from "react";
import { saveStrengthWorkout } from "./actions";
import { Card } from "@/components/ui/Card";

type ExerciseOption = {
  id: string;
  name: string;
  muscle_group: string;
};

type SetType = "reps" | "time";

type SetRow = {
  tempId: string;
  setType: SetType;
  actualWeight: string;
  actualReps: string;
  workSeconds: string;
  restSeconds: string;
  isWarmup: boolean;
};

type ExerciseEntry = {
  tempId: string;
  exerciseId: string;
  exerciseName: string;
  sets: SetRow[];
};

function newSetRow(): SetRow {
  return {
    tempId: crypto.randomUUID(),
    setType: "reps",
    actualWeight: "",
    actualReps: "",
    workSeconds: "",
    restSeconds: "",
    isWarmup: false,
  };
}

export function WorkoutBuilder({
  exercises,
}: {
  exercises: ExerciseOption[];
}) {
  const [title, setTitle] = useState("");
  const [entries, setEntries] = useState<ExerciseEntry[]>([]);
  const [filter, setFilter] = useState("");
  const [selectedExerciseId, setSelectedExerciseId] = useState(
    exercises[0]?.id ?? "",
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const groupedFiltered = useMemo(() => {
    const filtered = exercises.filter((e) =>
      e.name.toLowerCase().includes(filter.toLowerCase()),
    );
    const groups = new Map<string, ExerciseOption[]>();
    for (const exercise of filtered) {
      const group = groups.get(exercise.muscle_group) ?? [];
      group.push(exercise);
      groups.set(exercise.muscle_group, group);
    }
    return groups;
  }, [exercises, filter]);

  const filteredIds = useMemo(
    () => new Set([...groupedFiltered.values()].flat().map((e) => e.id)),
    [groupedFiltered],
  );

  function handleFilterChange(value: string) {
    setFilter(value);
    const stillVisible = exercises.some(
      (e) =>
        e.id === selectedExerciseId &&
        e.name.toLowerCase().includes(value.toLowerCase()),
    );
    if (!stillVisible) {
      const firstMatch = exercises.find((e) =>
        e.name.toLowerCase().includes(value.toLowerCase()),
      );
      setSelectedExerciseId(firstMatch?.id ?? "");
    }
  }

  function addExercise() {
    const exercise = exercises.find((e) => e.id === selectedExerciseId);
    if (!exercise) return;

    setEntries((prev) => [
      ...prev,
      {
        tempId: crypto.randomUUID(),
        exerciseId: exercise.id,
        exerciseName: exercise.name,
        sets: [],
      },
    ]);
  }

  function removeExercise(tempId: string) {
    setEntries((prev) => prev.filter((e) => e.tempId !== tempId));
  }

  function addSet(exerciseTempId: string) {
    setEntries((prev) =>
      prev.map((entry) =>
        entry.tempId === exerciseTempId
          ? { ...entry, sets: [...entry.sets, newSetRow()] }
          : entry,
      ),
    );
  }

  function removeSet(exerciseTempId: string, setTempId: string) {
    setEntries((prev) =>
      prev.map((entry) =>
        entry.tempId === exerciseTempId
          ? { ...entry, sets: entry.sets.filter((s) => s.tempId !== setTempId) }
          : entry,
      ),
    );
  }

  function updateSet(
    exerciseTempId: string,
    setTempId: string,
    field: keyof SetRow,
    value: string | boolean,
  ) {
    setEntries((prev) =>
      prev.map((entry) =>
        entry.tempId === exerciseTempId
          ? {
              ...entry,
              sets: entry.sets.map((s) =>
                s.tempId === setTempId ? { ...s, [field]: value } : s,
              ),
            }
          : entry,
      ),
    );
  }

  async function handleSave() {
    setError(null);

    if (entries.length === 0) {
      setError("Add at least one exercise.");
      return;
    }

    for (const entry of entries) {
      if (entry.sets.length === 0) {
        setError(`${entry.exerciseName} needs at least one set.`);
        return;
      }
      for (const set of entry.sets) {
        if (set.setType === "reps") {
          if (set.actualReps === "" || Number(set.actualReps) <= 0) {
            setError(`${entry.exerciseName}: every rep set needs reps > 0.`);
            return;
          }
          if (set.actualWeight === "" || Number(set.actualWeight) < 0) {
            setError(
              `${entry.exerciseName}: every rep set needs a weight (0 is fine for bodyweight).`,
            );
            return;
          }
        } else {
          if (set.workSeconds === "" || Number(set.workSeconds) <= 0) {
            setError(
              `${entry.exerciseName}: every timed set needs work seconds > 0.`,
            );
            return;
          }
        }
      }
    }

    setSaving(true);
    try {
      await saveStrengthWorkout({
        title,
        exercises: entries.map((entry) => ({
          exerciseId: entry.exerciseId,
          sets: entry.sets.map((s) =>
            s.setType === "reps"
              ? {
                  setType: "reps" as const,
                  actualWeight: Number(s.actualWeight),
                  actualReps: Number(s.actualReps),
                  isWarmup: s.isWarmup,
                }
              : {
                  setType: "time" as const,
                  workSeconds: Number(s.workSeconds),
                  restSeconds: s.restSeconds === "" ? null : Number(s.restSeconds),
                  actualWeight: s.actualWeight === "" ? null : Number(s.actualWeight),
                  isWarmup: s.isWarmup,
                },
          ),
        })),
      });
      // saveStrengthWorkout redirects on success — if we get here, redirect()
      // threw its special control-flow signal and this line won't run.
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
        placeholder="Workout title (optional)"
        className="rounded-xl border border-line bg-card px-3 py-2"
      />

      {error && (
        <p className="rounded-xl bg-coral-pale px-3 py-2 text-sm text-red">
          {error}
        </p>
      )}

      <div className="flex flex-col gap-2">
        <input
          value={filter}
          onChange={(e) => handleFilterChange(e.target.value)}
          placeholder="Filter exercises…"
          className="rounded-xl border border-line bg-card px-3 py-2"
        />
        <div className="flex gap-2">
          <select
            value={filteredIds.has(selectedExerciseId) ? selectedExerciseId : ""}
            onChange={(e) => setSelectedExerciseId(e.target.value)}
            className="flex-1 rounded-xl border border-line bg-card px-3 py-2"
          >
            {[...groupedFiltered.entries()].map(([group, groupExercises]) => (
              <optgroup key={group} label={group}>
                {groupExercises.map((exercise) => (
                  <option key={exercise.id} value={exercise.id}>
                    {exercise.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          <button
            type="button"
            onClick={addExercise}
            className="rounded-xl border border-line px-3 py-2 text-sm font-medium text-teal"
          >
            Add
          </button>
        </div>
      </div>

      {entries.map((entry) => (
        <Card key={entry.tempId} className="flex flex-col gap-2.5">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">{entry.exerciseName}</h2>
            <button
              type="button"
              onClick={() => removeExercise(entry.tempId)}
              className="font-mono text-xs text-red uppercase"
            >
              Remove
            </button>
          </div>

          {entry.sets.map((set, i) => (
            <div key={set.tempId} className="flex flex-wrap items-center gap-2">
              <span className="w-5 font-mono text-sm text-ink-soft">{i + 1}</span>

              <select
                value={set.setType}
                onChange={(e) =>
                  updateSet(entry.tempId, set.tempId, "setType", e.target.value)
                }
                className="rounded-lg border border-line px-2 py-1 font-mono text-xs"
              >
                <option value="reps">reps</option>
                <option value="time">timed</option>
              </select>

              {set.setType === "reps" ? (
                <>
                  <input
                    type="number"
                    inputMode="decimal"
                    placeholder="Weight"
                    value={set.actualWeight}
                    onChange={(e) =>
                      updateSet(entry.tempId, set.tempId, "actualWeight", e.target.value)
                    }
                    className="w-20 rounded-lg border border-line px-2 py-1"
                  />
                  <input
                    type="number"
                    inputMode="numeric"
                    placeholder="Reps"
                    value={set.actualReps}
                    onChange={(e) =>
                      updateSet(entry.tempId, set.tempId, "actualReps", e.target.value)
                    }
                    className="w-20 rounded-lg border border-line px-2 py-1"
                  />
                </>
              ) : (
                <>
                  <input
                    type="number"
                    inputMode="numeric"
                    placeholder="Work (sec)"
                    value={set.workSeconds}
                    onChange={(e) =>
                      updateSet(entry.tempId, set.tempId, "workSeconds", e.target.value)
                    }
                    className="w-24 rounded-lg border border-line px-2 py-1"
                  />
                  <input
                    type="number"
                    inputMode="numeric"
                    placeholder="Rest (sec)"
                    value={set.restSeconds}
                    onChange={(e) =>
                      updateSet(entry.tempId, set.tempId, "restSeconds", e.target.value)
                    }
                    className="w-24 rounded-lg border border-line px-2 py-1"
                  />
                  <input
                    type="number"
                    inputMode="decimal"
                    placeholder="Weight (opt.)"
                    value={set.actualWeight}
                    onChange={(e) =>
                      updateSet(entry.tempId, set.tempId, "actualWeight", e.target.value)
                    }
                    className="w-24 rounded-lg border border-line px-2 py-1"
                  />
                </>
              )}

              <label className="flex items-center gap-1 font-mono text-xs text-ink-soft">
                <input
                  type="checkbox"
                  checked={set.isWarmup}
                  onChange={(e) =>
                    updateSet(entry.tempId, set.tempId, "isWarmup", e.target.checked)
                  }
                />
                warmup
              </label>
              <button
                type="button"
                onClick={() => removeSet(entry.tempId, set.tempId)}
                className="ml-auto text-red"
              >
                ×
              </button>
            </div>
          ))}

          <button
            type="button"
            onClick={() => addSet(entry.tempId)}
            className="self-start font-mono text-xs tracking-wide text-teal uppercase"
          >
            + Add set
          </button>
        </Card>
      ))}

      <button
        type="button"
        onClick={handleSave}
        disabled={saving}
        className="rounded-full bg-teal px-4 py-2.5 font-medium text-white disabled:opacity-50"
      >
        {saving ? "Saving…" : "Save workout"}
      </button>
    </div>
  );
}
