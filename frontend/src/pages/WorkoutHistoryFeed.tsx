import { useMemo, useState } from "react";

import { useDeleteWorkout, useWorkoutHistory } from "../api/dashboard";
import type { components } from "../api/generated";
import {
  dateFromIso,
  daysBetween,
  isoDateInTz,
  isoFromDate,
  todayIsoInTz,
  useUserTimezone,
} from "../lib/datetime";

type Workout = components["schemas"]["WorkoutOut"];
type Set = components["schemas"]["SetOut"];

// How far back the history feed looks. Not user-adjustable yet — a good default
// for "what have I been doing lately" without pagination.
const HISTORY_WINDOW_DAYS = 90;

// "Today" / "Yesterday" / "Monday" / "Mar 4" — all relative to the user's zone, so
// an evening workout doesn't read as "tomorrow" and the day-of-week matches the
// calendar the backend bucketed it into.
function relativeDay(startedAt: string, tz: string): string {
  const dayIso = isoDateInTz(startedAt, tz);
  const diffDays = daysBetween(dayIso, todayIsoInTz(tz));
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  const dayOnly = dateFromIso(dayIso);
  if (diffDays > 1 && diffDays < 7) {
    return dayOnly.toLocaleDateString(undefined, { weekday: "long" });
  }
  return dayOnly.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function workoutTitle(w: Workout): string {
  return w.title ?? (w.workout_type === "strength" ? "Strength workout" : (w.activity_type ?? "Workout"));
}

function totalSets(w: Workout): number {
  return w.exercises.reduce((n, e) => n + e.sets.length, 0);
}

function formatCalories(w: Workout): string | null {
  return w.calories_burned != null ? `~${Math.round(Number(w.calories_burned))} kcal (est.)` : null;
}

function formatSet(s: Set): string {
  const base = s.set_type === "time" ? `${s.work_seconds}s` : `${s.weight ?? "—"}lbs × ${s.reps}`;
  return s.is_warmup ? `${base} (warmup)` : base;
}

function WorkoutCard({ w }: { w: Workout }) {
  const [open, setOpen] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const isStrength = w.workout_type === "strength";
  const sets = isStrength ? totalSets(w) : 0;
  const deleteWorkout = useDeleteWorkout();
  const tz = useUserTimezone();

  return (
    <div className="workout-history-card">
      <button type="button" className="workout-history-card-toggle" onClick={() => setOpen((o) => !o)}>
        <div className="workout-history-card-main">
          <span className="workout-history-day muted">{relativeDay(w.started_at, tz)}</span>
          <strong>{workoutTitle(w)}</strong>
          <span className="muted workout-history-stats">
            {w.duration_minutes != null && `${w.duration_minutes} min`}
            {isStrength &&
              sets > 0 &&
              `${w.exercises.length} exercise${w.exercises.length === 1 ? "" : "s"}, ${sets} set${sets === 1 ? "" : "s"}`}
          </span>
        </div>
        <span className="workout-history-chevron">{open ? "▾" : "▸"}</span>
      </button>

      {open && (
        <div className="workout-history-detail">
          {isStrength ? (
            <>
              {formatCalories(w) && (
                <p className="muted" style={{ margin: "0 0 0.5rem" }}>
                  {formatCalories(w)}
                </p>
              )}
              {w.exercises.length > 0 ? (
                w.exercises.map((e) => (
                  <div key={e.id} className="workout-history-exercise">
                    <span className="workout-history-exercise-name">
                      {e.exercise_name ?? "Exercise"}
                    </span>
                    <span className="muted workout-history-exercise-sets">
                      {e.sets.map(formatSet).join(", ")}
                    </span>
                  </div>
                ))
              ) : (
                <p className="muted" style={{ margin: 0 }}>
                  No exercises logged.
                </p>
              )}
            </>
          ) : (
            <p className="muted" style={{ margin: 0 }}>
              {formatCalories(w)}
              {w.notes && ` — ${w.notes}`}
            </p>
          )}

          {confirmingDelete ? (
            <div className="workout-history-delete-confirm">
              <span>Delete this workout? This can't be undone.</span>
              <div className="workout-history-delete-confirm-actions">
                <button
                  type="button"
                  onClick={() => deleteWorkout.mutate(w.id)}
                  disabled={deleteWorkout.isPending}
                >
                  {deleteWorkout.isPending ? "Deleting…" : "Delete"}
                </button>
                <button type="button" onClick={() => setConfirmingDelete(false)}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              className="workout-history-delete-btn"
              onClick={() => setConfirmingDelete(true)}
            >
              Delete workout
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function WorkoutHistoryFeed() {
  const tz = useUserTimezone();
  const end = useMemo(() => todayIsoInTz(tz), [tz]);
  const start = useMemo(() => {
    const d = dateFromIso(end);
    d.setDate(d.getDate() - HISTORY_WINDOW_DAYS);
    return isoFromDate(d);
  }, [end]);
  const history = useWorkoutHistory(start, end);

  return (
    <div className="workout-history">
      <h3>History</h3>
      {history.isPending && <p className="muted">Loading history…</p>}
      {history.isError && <p className="error">Couldn't load workout history.</p>}
      {history.data && (
        <WorkoutHistoryList workouts={history.data.filter((w) => w.completed_at != null)} />
      )}
    </div>
  );
}

function WorkoutHistoryList({ workouts }: { workouts: Workout[] }) {
  if (workouts.length === 0) {
    return <p className="muted">No workouts logged yet.</p>;
  }
  return (
    <div className="workout-history-feed">
      {workouts.map((w) => (
        <WorkoutCard key={w.id} w={w} />
      ))}
    </div>
  );
}
