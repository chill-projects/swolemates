import { useCallback } from "react";

import { api } from "../api/client";
import { AppRenderer, type ToolResultPayload } from "../mcp-apps/AppRenderer";
import type { components } from "../api/generated";

type WorkoutLiveOut = components["schemas"]["WorkoutLiveOut"];
type ExerciseEntryOut = components["schemas"]["ExerciseEntryOut"];
interface Me {
  user_sub: string;
  email: string | null;
  display_name: string | null;
}

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

function toLivePayload(live: WorkoutLiveOut): ToolResultPayload {
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
  };
  return { content: [{ type: "text", text: JSON.stringify(payload) }], structuredContent: payload };
}

const emptyPayload: ToolResultPayload = {
  content: [{ type: "text", text: "No active workout." }],
  structuredContent: { active: false, summary: "No active workout." },
};

export function WorkoutLivePage({ me }: { me: Me }) {
  const handleTool = useCallback(
    async (name: string, args: Record<string, unknown>): Promise<ToolResultPayload> => {
      if (name === "list_workout_exercises") {
        const { data, error } = await api.GET("/api/workouts/exercises");
        if (error || !data) throw new Error("exercises fetch failed");
        const payload = {
          exercises: data.map((e) => ({ id: e.id, name: e.name, muscle_group: e.muscle_group })),
        };
        return { content: [{ type: "text", text: JSON.stringify(payload) }], structuredContent: payload };
      }

      switch (name) {
        case "get_active_workout":
          break;
        case "start_workout": {
          const { error } = await api.POST("/api/workouts/start", {
            body: {
              exercises: (args.exercises as string[] | undefined) ?? null,
              template_id: (args.template_id as string | undefined) ?? null,
            },
          });
          if (error) throw new Error("start workout failed");
          break;
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
          break;
        }
        case "finish_workout": {
          const { error } = await api.POST("/api/workouts/{workout_id}/finish", {
            params: { path: { workout_id: String(args.workout_id ?? "") } },
            body: {},
          });
          if (error) throw new Error("finish workout failed");
          break;
        }
        case "update_workout_entry": {
          const { error } = await api.POST("/api/workouts/{workout_id}/entries", {
            params: { path: { workout_id: String(args.workout_id ?? "") } },
            body: {
              action: String(args.action ?? ""),
              exercise: (args.exercise as string | undefined) ?? null,
              workout_exercise_id: (args.workout_exercise_id as string | undefined) ?? null,
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

      const active = await api.GET("/api/workouts/active");
      if (active.error) throw new Error("active fetch failed");
      if (!active.data) return emptyPayload;

      const live = await api.GET("/api/workouts/{workout_id}/live", {
        params: { path: { workout_id: active.data.id } },
      });
      if (live.error || !live.data) throw new Error("live fetch failed");
      return toLivePayload(live.data);
    },
    [],
  );

  return (
    <section>
      <p className="muted">
        Signed in as <strong>{me.display_name ?? me.email ?? me.user_sub}</strong> ✓
      </p>
      <AppRenderer
        bundleUrl="/mcp-apps/workout-live.html"
        initialTool="get_active_workout"
        onCallTool={handleTool}
        eventsUrl="/api/workouts/events"
      />
    </section>
  );
}
