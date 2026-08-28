import { useCallback, useState } from "react";

import { api } from "../api/client";
import { useSetWeeklyPattern, useTemplates, useWeeklyPattern } from "../api/plan";
import type { components } from "../api/generated";
import { Card, PageHero } from "../components/ui";
import { AppRenderer, type ToolResultPayload } from "../mcp-apps/AppRenderer";

type TemplateOut = components["schemas"]["TemplateOut"];
type TemplateExerciseOut = components["schemas"]["TemplateExerciseOut"];
type PatternDay = components["schemas"]["WeeklyPatternDayOut"];

// Monday-first, matching the backend's week boundary (celebrations.py::_week_bounds
// uses Python's weekday(), Mon=0) and the pattern's own day_of_week numbering.
const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const numeric = (v: string | null | undefined) => (v == null ? null : Number(v));

function toExercisePayload(e: TemplateExerciseOut) {
  return {
    id: e.id,
    exercise_id: e.exercise_id,
    exercise_name: e.exercise_name,
    superset_group: e.superset_group,
    sets: e.sets,
    reps: e.reps,
    seconds: e.seconds,
    weight: numeric(e.weight),
    notes: e.notes,
  };
}

function toTemplatePayload(t: TemplateOut): ToolResultPayload {
  const payload = {
    id: t.id,
    name: t.name,
    description: t.description,
    exercises: t.exercises.map(toExercisePayload),
  };
  return { content: [{ type: "text", text: JSON.stringify(payload) }], structuredContent: payload };
}

function toPayload(key: string, data: unknown): ToolResultPayload {
  const payload = { [key]: data };
  return { content: [{ type: "text", text: JSON.stringify(payload) }], structuredContent: payload };
}

/** "Four lifting days, three rest." — the pattern read back as a sentence. */
function patternHeadline(pattern: PatternDay[] | undefined): string {
  if (!pattern) return "Your week, one pattern.";
  const lifting = pattern.filter((d) => d.template_id !== null).length;
  const rest = 7 - lifting;
  if (lifting === 0) return "Nothing scheduled yet.";
  const word = (n: number) => ["no", "one", "two", "three", "four", "five", "six", "seven"][n] ?? n;
  return `${String(word(lifting)).replace(/^./, (c) => c.toUpperCase())} lifting ${
    lifting === 1 ? "day" : "days"
  }, ${word(rest)} rest.`;
}

/**
 * Plan (5a) — the weekly pattern, the seven days it generates, and the template
 * library in one tab. Replaces the separate Planned and Templates pages: the
 * pattern decides which template runs on which day, the next seven days come from
 * it, and the library below is where a template gets edited.
 */
export function PlanPage() {
  const pattern = useWeeklyPattern();
  const templates = useTemplates();
  const setPattern = useSetWeeklyPattern();
  const [editingId, setEditingId] = useState<string | null>(null);

  const byDay = new Map((pattern.data ?? []).map((d) => [d.day_of_week, d]));

  /** The pattern is written whole, so one day's change carries the other six. */
  function setDay(dayOfWeek: number, templateId: string | null) {
    const days = Array.from({ length: 7 }, (_, i) => ({
      day_of_week: i,
      template_id: i === dayOfWeek ? templateId : (byDay.get(i)?.template_id ?? null),
    }));
    setPattern.mutate(days);
  }

  /** Which weekdays a template is scheduled on — the chip beside its name. */
  function daysFor(templateId: string): string[] {
    return (pattern.data ?? [])
      .filter((d) => d.template_id === templateId)
      .map((d) => DAY_LABELS[d.day_of_week] ?? "")
      .filter(Boolean);
  }

  const plannedTools = useCallback(
    async (name: string, args: Record<string, unknown>): Promise<ToolResultPayload> => {
      switch (name) {
        case "get_planned_workouts": {
          const { data, error } = await api.GET("/api/planned-workouts");
          if (error || !data) throw new Error("planned fetch failed");
          return toPayload("planned", data);
        }
        case "update_planned_workout": {
          const { error } = await api.POST("/api/planned-workouts/{planned_id}/entries", {
            params: { path: { planned_id: String(args.planned_id ?? "") } },
            body: { action: String(args.action ?? "") },
          });
          if (error) throw new Error("update planned workout failed");
          const { data, error: listError } = await api.GET("/api/planned-workouts");
          if (listError || !data) throw new Error("planned fetch failed");
          return toPayload("planned", data);
        }
        case "start_workout": {
          const { error } = await api.POST("/api/workouts/start", {
            body: { planned_id: (args.planned_id as string | undefined) ?? null },
          });
          if (error) throw new Error("start workout failed");
          return { content: [{ type: "text", text: "Started." }] };
        }
        // The pattern is edited in the band above, in React — but the component
        // still asks for these on load, and does own them in a chat host.
        case "list_templates_catalog": {
          const { data, error } = await api.GET("/api/templates");
          if (error || !data) throw new Error("templates fetch failed");
          return toPayload("templates", data.map((t) => ({ id: t.id, name: t.name })));
        }
        case "get_weekly_pattern": {
          const { data, error } = await api.GET("/api/weekly-pattern");
          if (error || !data) throw new Error("pattern fetch failed");
          return toPayload("pattern", data);
        }
        case "set_weekly_pattern": {
          const days =
            (args.days as { day_of_week: number; template_id: string | null }[] | undefined) ?? [];
          const { data, error } = await api.PUT("/api/weekly-pattern", { body: { days } });
          if (error || !data) throw new Error("set pattern failed");
          return toPayload("pattern", data);
        }
        default:
          throw new Error(`unknown tool: ${name}`);
      }
    },
    [],
  );

  const templateTools = useCallback(
    async (name: string, args: Record<string, unknown>): Promise<ToolResultPayload> => {
      if (name === "list_exercise_catalog") {
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

      if (name === "archive_workout_template") {
        const templateId = String(args.template_id ?? editingId ?? "");
        const { error } = await api.POST("/api/templates/{template_id}/archive", {
          params: { path: { template_id: templateId } },
        });
        if (error) throw new Error("archive failed");
        setEditingId(null);
        void templates.refetch();
        return { content: [{ type: "text", text: "Archived." }] };
      }

      let templateId: string;
      switch (name) {
        case "get_workout_template":
          templateId = String(args.template_id ?? editingId ?? "");
          break;
        case "update_workout_template": {
          templateId = String(args.template_id ?? editingId ?? "");
          const { error } = await api.POST("/api/templates/{template_id}/entries", {
            params: { path: { template_id: templateId } },
            body: {
              action: String(args.action ?? ""),
              name: (args.name as string | undefined) ?? null,
              exercise: (args.exercise as string | undefined) ?? null,
              template_exercise_id: (args.template_exercise_id as string | undefined) ?? null,
              superset_with: (args.superset_with as string | undefined) ?? null,
              order: (args.order as string[] | undefined) ?? null,
              sets: (args.sets as number | undefined) ?? null,
              reps: (args.reps as number | undefined) ?? null,
              seconds: (args.seconds as number | undefined) ?? null,
              weight: (args.weight as number | undefined) ?? null,
              notes: (args.notes as string | undefined) ?? null,
            },
          });
          if (error) throw new Error("update template failed");
          void templates.refetch();
          break;
        }
        default:
          throw new Error(`unknown tool: ${name}`);
      }

      const { data, error } = await api.GET("/api/templates/{template_id}", {
        params: { path: { template_id: templateId } },
      });
      if (error || !data) throw new Error("template fetch failed");
      return toTemplatePayload(data);
    },
    [editingId, templates],
  );

  const editing = templates.data?.find((t) => t.id === editingId);

  return (
    <>
      <PageHero
        eyebrow="Weekly pattern · saves as you change it"
        title={patternHeadline(pattern.data)}
        lead="Pick a template for each day. Everything below is generated from this — change a day and the next seven days follow."
        below={
          <div className="pattern-grid">
            {DAY_LABELS.map((label, i) => {
              const day = byDay.get(i);
              const active = day?.template_id != null;
              return (
                <label
                  key={label}
                  className={active ? "pattern-day pattern-day--active" : "pattern-day"}
                >
                  <span className="pattern-day-name">{label}</span>
                  <span className="pattern-day-template">{day?.template_name ?? "Rest"}</span>
                  {/* The select is the control; the cell is its face. Keeping a real
                      <select> means keyboard and screen-reader behaviour come free. */}
                  <select
                    aria-label={`${label} template`}
                    value={day?.template_id ?? ""}
                    disabled={pattern.isPending || setPattern.isPending}
                    onChange={(e) => setDay(i, e.target.value || null)}
                  >
                    <option value="">Rest</option>
                    {(templates.data ?? []).map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </label>
              );
            })}
          </div>
        }
      />

      <div className="page-body">
        {pattern.isError && <p className="error">Couldn’t load your weekly pattern.</p>}
        {setPattern.isError && <p className="error">Couldn’t save that change.</p>}

        <div className="page-grid page-grid--split">
          <div className="page-grid">
            <AppRenderer
              bundleUrl="/mcp-apps/planned.html"
              initialTool="get_planned_workouts"
              onCallTool={plannedTools}
              eventsUrl="/api/workouts/events"
            />
          </div>

          <div className="page-grid">
            <Card
              title="Templates"
              meta={
                <span className="card-meta">
                  {templates.data ? `${templates.data.length} saved` : ""}
                </span>
              }
            >
              {templates.isPending && <p className="muted">Loading…</p>}
              {templates.data?.length === 0 && (
                <p className="card-note">
                  No templates yet — ask Claude for “a pull day” and it shows up here.
                </p>
              )}
              <ul className="template-rows">
                {templates.data?.map((t) => {
                  const days = daysFor(t.id);
                  return (
                    <li key={t.id}>
                      <div className="row-main">
                        <div className="row-name">
                          {t.name}
                          <span className={days.length ? "chip chip--teal" : "chip"}>
                            {days.length ? days.join(", ") : "unscheduled"}
                          </span>
                        </div>
                        <div className="row-detail">
                          {t.exercises.length} exercise{t.exercises.length === 1 ? "" : "s"}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => setEditingId(editingId === t.id ? null : t.id)}
                      >
                        {editingId === t.id ? "Done" : "Edit"}
                      </button>
                    </li>
                  );
                })}
              </ul>
              <p className="card-note">
                New templates come from chat — ask Claude for “a pull day”.
              </p>
            </Card>

            {editingId && (
              <Card
                title={editing?.name ?? "Template"}
                meta={
                  <span className="card-meta">
                    {daysFor(editingId).length
                      ? `every ${daysFor(editingId).join(", ")}`
                      : "unscheduled"}
                  </span>
                }
              >
                <AppRenderer
                  key={editingId}
                  bundleUrl="/mcp-apps/template.html"
                  initialTool="get_workout_template"
                  onCallTool={templateTools}
                />
              </Card>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
