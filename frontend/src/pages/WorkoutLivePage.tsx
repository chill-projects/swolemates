import { useCallback, useState } from "react";

import { api } from "../api/client";
import { PageHero } from "../components/ui";
import { AppRenderer, type ToolResultPayload } from "../mcp-apps/AppRenderer";
import type { components } from "../api/generated";
import { todayIsoInTz, useUserTimezone } from "../lib/datetime";
import { WorkoutHistoryFeed } from "./WorkoutHistoryFeed";

type WorkoutLiveOut = components["schemas"]["WorkoutLiveOut"];
type ExerciseEntryOut = components["schemas"]["ExerciseEntryOut"];
type WorkoutOut = components["schemas"]["WorkoutOut"];

const numeric = (v: string | null | undefined) => (v == null ? null : Number(v));

/** Shape a REST `WorkoutLiveOut` into the same payload the MCP tools return
 *  (numbers instead of the Decimal-as-string REST wire format), so the
 *  component can't tell which host it's running in. */
function toExercisePayload(e: ExerciseEntryOut) {
  return {
    id: e.id,
    exercise_id: e.exercise_id,
    exercise_name: e.exercise_name,
    next_time_note: e.next_time_note,
    sets: e.sets.map((s) => ({
      id: s.id,
      set_number: s.set_number,
      set_type: s.set_type,
      is_warmup: s.is_warmup,
      weight: numeric(s.weight),
      reps: s.reps,
      work_seconds: s.work_seconds,
    })),
    last_time: e.last_time
      ? {
          sets: e.last_time.sets.map((s) => ({ weight: numeric(s.weight), reps: s.reps })),
          note: e.last_time.note,
        }
      : null,
    target: e.target
      ? {
          sets: e.target.sets,
          reps: e.target.reps,
          seconds: e.target.seconds,
          weight: numeric(e.target.weight),
        }
      : null,
  };
}

/**
 * `earnedCelebrations`/`earnedStreak` override `live`'s own (always-empty, since a
 * plain re-read never earns anything) values — see the comment at the `/live`
 * call site for why these have to be threaded through separately.
 */
function toLivePayload(
  live: WorkoutLiveOut,
  earnedCelebrations?: WorkoutOut["celebrations"] | null,
  earnedStreak?: WorkoutOut["streak"] | null,
): ToolResultPayload {
  const celebrations = earnedCelebrations ?? live.celebrations;
  const streak = earnedStreak ?? live.streak;
  const payload = {
    active: true,
    id: live.id,
    completed_at: live.completed_at,
    groups: live.groups.map((g) => ({
      superset_group: g.superset_group,
      is_superset: g.is_superset,
      exercises: g.exercises.map(toExercisePayload),
    })),
    summary: live.summary,
    celebrations: celebrations.map((c) => ({
      exercise_name: c.exercise_name,
      kind: c.kind,
      value: numeric(c.value),
      previous: numeric(c.previous),
    })),
    streak: streak ? { weeks: streak.weeks, this_week: streak.this_week, target: streak.target } : null,
    muscle_coverage: live.muscle_coverage.map((c) => ({ muscle: c.muscle, level: c.level })),
  };
  return { content: [{ type: "text", text: JSON.stringify(payload) }], structuredContent: payload };
}

const emptyPayload: ToolResultPayload = {
  content: [{ type: "text", text: "No active workout." }],
  structuredContent: { active: false, summary: "No active workout." },
};

/** The subset of the live payload the hero band reads. Same object the component
 *  inside the iframe is rendering — see AppRenderer's `onResult`. */
type LiveState = {
  active: boolean;
  summary: string;
  groups?: { exercises: { exercise_name: string; sets: unknown[] }[] }[];
};

function isLiveState(value: unknown): value is LiveState {
  return typeof value === "object" && value !== null && "active" in value && "summary" in value;
}

type PlanState = { planned: { template_name: string } | null };

function isPlanState(value: unknown): value is PlanState {
  return typeof value === "object" && value !== null && "planned" in value;
}

export function WorkoutLivePage() {
  const tz = useUserTimezone();
  const [live, setLive] = useState<LiveState | null>(null);
  const [plan, setPlan] = useState<string | null>(null);
  const handleTool = useCallback(
    async (name: string, args: Record<string, unknown>): Promise<ToolResultPayload> => {
      if (name === "list_workout_exercises") {
        const { data, error } = await api.GET("/api/workouts/exercises");
        if (error || !data) throw new Error("exercises fetch failed");
        const payload = {
          exercises: data.map((e) => ({
            id: e.id,
            name: e.name,
            muscle_group: e.muscle_group,
            equipment: e.equipment,
          })),
        };
        return { content: [{ type: "text", text: JSON.stringify(payload) }], structuredContent: payload };
      }

      if (name === "log_activity") {
        const { data, error } = await api.POST("/api/workouts/log-activity", {
          body: {
            activity_type: String(args.activity_type ?? ""),
            duration_minutes: Number(args.duration_minutes ?? 0),
            notes: (args.notes as string | null | undefined) ?? null,
          },
        });
        if (error || !data) throw new Error("log activity failed");
        const streak = data.streak
          ? ` — ${data.streak.weeks}-week streak, ${data.streak.this_week}/${data.streak.target} this week`
          : "";
        const calories = numeric(data.calories_burned);
        const kcal = calories != null ? ` — ~${calories} kcal (est.)` : "";
        const text = `Logged: ${data.activity_type} — ${data.duration_minutes} min${kcal}${streak}`;
        return { content: [{ type: "text", text }] };
      }

      // `/live` (fetched below, for the grouped accordion shape) is a plain re-read
      // of current state — it has no memory of what a specific mutation just earned.
      // celebrations/streak only ever appear on the response of the exact call that
      // produced them (log_set/finish_workout), so that response's own values are
      // captured here and merged into the freshly-fetched live payload afterward.
      let earnedCelebrations: WorkoutOut["celebrations"] | null = null;
      let earnedStreak: WorkoutOut["streak"] | null = null;
      // Which workout to fetch /live for. Left null to fall back to /active below —
      // but finish_workout's own workout is no longer active once it's finished, so
      // that case sets this explicitly rather than losing the id (and the earned
      // streak) to a "no active workout" short-circuit.
      let workoutId: string | null = null;

      switch (name) {
        case "get_active_workout":
          break;
        case "start_workout": {
          const { error } = await api.POST("/api/workouts/start", {
            body: {
              exercises: (args.exercises as string[] | undefined) ?? null,
              template_id: (args.template_id as string | undefined) ?? null,
              planned_id: (args.planned_id as string | undefined) ?? null,
            },
          });
          if (error) throw new Error("start workout failed");
          break;
        }
        case "get_todays_plan": {
          // "Today" in the user's zone — a UTC date rolls to tomorrow in the evening
          // west of UTC, so "today's plan" would show tomorrow's.
          const today = todayIsoInTz(tz);
          const { data, error } = await api.GET("/api/planned-workouts", {
            params: { query: { start: today, end: today } },
          });
          if (error || !data) throw new Error("planned fetch failed");
          const entry = data.find((p) => p.status === "planned");
          // exercise_names comes along so the idle screen can show what the plan
          // actually is, rather than just its name.
          const payload = {
            planned: entry
              ? {
                  id: entry.id,
                  template_name: entry.template_name,
                  exercise_names: entry.exercise_names,
                }
              : null,
          };
          return { content: [{ type: "text", text: JSON.stringify(payload) }], structuredContent: payload };
        }
        case "list_templates_catalog": {
          const { data, error } = await api.GET("/api/templates");
          if (error || !data) throw new Error("templates fetch failed");
          const payload = {
            templates: data.map((t) => ({
              id: t.id,
              name: t.name,
              exercise_count: t.exercises.length,
              set_count: t.exercises.reduce((n, e) => n + (e.sets ?? 0), 0),
            })),
          };
          return { content: [{ type: "text", text: JSON.stringify(payload) }], structuredContent: payload };
        }
        case "log_set": {
          const { data, error } = await api.POST("/api/workouts/log-set", {
            body: {
              exercise: String(args.exercise ?? ""),
              reps: (args.reps as number | undefined) ?? null,
              weight: (args.weight as number | undefined) ?? null,
              is_warmup: (args.is_warmup as boolean | undefined) ?? false,
              set_type: (args.set_type as string | undefined) ?? "reps",
              work_seconds: (args.work_seconds as number | undefined) ?? null,
              sets: 1,
            },
          });
          if (error) throw new Error("log set failed");
          if (data.needs_clarification) {
            return { content: [{ type: "text", text: data.needs_clarification }] };
          }
          earnedCelebrations = data.workout?.celebrations ?? null;
          break;
        }
        case "finish_workout": {
          const finishedId = String(args.workout_id ?? "");
          const { data, error } = await api.POST("/api/workouts/{workout_id}/finish", {
            params: { path: { workout_id: finishedId } },
            body: {},
          });
          if (error) throw new Error("finish workout failed");
          // No exercises were ever added — the server discarded it rather than
          // persisting an empty completed row, so there's no /live to re-fetch.
          if (!data) return emptyPayload;
          earnedStreak = data.streak ?? null;
          workoutId = finishedId;
          break;
        }
        case "update_workout_entry": {
          const { error } = await api.POST("/api/workouts/{workout_id}/entries", {
            params: { path: { workout_id: String(args.workout_id ?? "") } },
            body: {
              action: String(args.action ?? ""),
              exercise: (args.exercise as string | undefined) ?? null,
              workout_exercise_id: (args.workout_exercise_id as string | undefined) ?? null,
              workout_set_id: (args.workout_set_id as string | undefined) ?? null,
              superset_with: (args.superset_with as string | undefined) ?? null,
              order: (args.order as string[] | undefined) ?? null,
              note: (args.note as string | undefined) ?? null,
            },
          });
          if (error) throw new Error("update workout entry failed");
          break;
        }
        default:
          throw new Error(`unknown tool: ${name}`);
      }

      if (workoutId === null) {
        const active = await api.GET("/api/workouts/active");
        if (active.error) throw new Error("active fetch failed");
        if (!active.data) return emptyPayload;
        workoutId = active.data.id;
      }

      const live = await api.GET("/api/workouts/{workout_id}/live", {
        params: { path: { workout_id: workoutId } },
      });
      if (live.error || !live.data) throw new Error("live fetch failed");
      return toLivePayload(live.data, earnedCelebrations, earnedStreak);
    },
    [tz],
  );

  const exercises = live?.groups?.flatMap((g) => g.exercises) ?? [];
  const sets = exercises.reduce((n, e) => n + e.sets.length, 0);
  // The one you're on is the last one you've actually logged against — not the last
  // in the list, which for a template-started workout is the whole plan sitting
  // there empty. Falls back to the first exercise before any set exists.
  const current =
    exercises.filter((e) => e.sets.length > 0).at(-1)?.exercise_name ??
    exercises[0]?.exercise_name;

  return (
    <>
      <PageHero
        eyebrow={
          live?.active
            ? `In progress · ${sets} ${sets === 1 ? "set" : "sets"} logged`
            : "Nothing running"
        }
        title={
          live?.active && current
            ? `Mid-session on ${current.toLowerCase()}.`
            : plan
              ? `${plan} is on the plan for today.`
              : "Nothing on the plan for today."
        }
        // No lead while a workout is running: the eyebrow already carries the set
        // count, and the component below prints its own summary line.
        lead={
          live?.active
            ? undefined
            : "Start from the plan, pick a template, or log an activity instead."
        }
      />
      <div className="page-body">
        <AppRenderer
          bundleUrl="/mcp-apps/workout-live.html"
          initialTool="get_active_workout"
          onCallTool={handleTool}
          // Every tool result comes through here; keep whichever shape each one is.
          onResult={(result) => {
            const payload = result.structuredContent;
            if (isLiveState(payload)) setLive(payload);
            else if (isPlanState(payload)) setPlan(payload.planned?.template_name ?? null);
          }}
          eventsUrl="/api/workouts/events"
        />
        <WorkoutHistoryFeed />
      </div>
    </>
  );
}
