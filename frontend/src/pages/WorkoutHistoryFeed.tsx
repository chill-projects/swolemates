import { useMemo, useState } from "react";

import { useWorkoutHistory } from "../api/dashboard";
import type { components } from "../api/generated";

type Workout = components["schemas"]["WorkoutOut"];
type Set = components["schemas"]["SetOut"];

// How far back the history feed looks. Not user-adjustable yet — a good default
// for "what have I been doing lately" without pagination.
const HISTORY_WINDOW_DAYS = 90;

// Local-date, not UTC — `toISOString()` rolls to the next UTC day before local
// midnight, mislabeling "today" as tomorrow for anyone west of UTC in the
// evening (see the nutrition-day "today" fix).
function localIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function relativeDay(startedAt: string): string {
  const d = new Date(startedAt);
  const dayOnly = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const today = new Date();
  const todayOnly = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const diffDays = Math.round((todayOnly.getTime() - dayOnly.getTime()) / 86_400_000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return dayOnly.toLocaleDateString(undefined, { weekday: "long" });
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
  const isStrength = w.workout_type === "strength";
  const sets = isStrength ? totalSets(w) : 0;

  return (
    <div className="workout-history-card">
      <button type="button" className="workout-history-card-toggle" onClick={() => setOpen((o) => !o)}>
        <div className="workout-history-card-main">
          <span className="workout-history-day muted">{relativeDay(w.started_at)}</span>
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
        </div>
      )}
    </div>
  );
}

export function WorkoutHistoryFeed() {
  const end = useMemo(() => localIsoDate(new Date()), []);
  const start = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - HISTORY_WINDOW_DAYS);
    return localIsoDate(d);
  }, []);
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
