import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import { InfoPopover } from "../components/InfoPopover";
import { AppRenderer, type ToolResultPayload } from "../mcp-apps/AppRenderer";
import type { components } from "../api/generated";

type TemplateOut = components["schemas"]["TemplateOut"];
type TemplateExerciseOut = components["schemas"]["TemplateExerciseOut"];
interface Me {
  user_sub: string;
  email: string | null;
  display_name: string | null;
}

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

/**
 * No template-creation UI here: per the resolved design doc, templates are created
 * conversationally in chat ("make me a pull day"), not via an SPA wizard. This page
 * only lists existing templates and hosts the shared editor component for whichever
 * one is selected.
 */
export function TemplatesPage({ me }: { me: Me }) {
  const [templates, setTemplates] = useState<TemplateOut[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const refreshList = useCallback(async () => {
    const { data } = await api.GET("/api/templates");
    setTemplates(data ?? []);
  }, []);

  useEffect(() => {
    void refreshList();
  }, [refreshList]);

  const handleTool = useCallback(
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
        const templateId = String(args.template_id ?? selectedId ?? "");
        const { error } = await api.POST("/api/templates/{template_id}/archive", {
          params: { path: { template_id: templateId } },
        });
        if (error) throw new Error("archive failed");
        setSelectedId(null);
        void refreshList();
        return { content: [{ type: "text", text: "Archived." }] };
      }

      let templateId: string;
      switch (name) {
        case "get_workout_template":
          templateId = String(args.template_id ?? selectedId ?? "");
          break;
        case "update_workout_template": {
          templateId = String(args.template_id ?? selectedId ?? "");
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
          void refreshList();
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
    [selectedId, refreshList],
  );

  return (
    <section>
      <h2>
        Templates
        <InfoPopover label="How the Templates page works">
          <p className="info-popover-title">Templates</p>
          <p className="muted">
            Templates aren't created here — ask Claude to make you one (e.g. "make me a
            pull day") and it'll show up in the list on the right.
          </p>
          <p className="muted">Select a template to view and edit its exercises.</p>
        </InfoPopover>
      </h2>
      <p className="muted">
        Signed in as <strong>{me.display_name ?? me.email ?? me.user_sub}</strong> ✓
      </p>
      <div style={{ display: "flex", gap: "1.5rem", justifyContent: "center" }}>
        <div className="dash-card" style={{ flex: 1, maxWidth: "26rem", alignSelf: "flex-start" }}>
          {selectedId ? (
            <AppRenderer
              key={selectedId}
              bundleUrl="/mcp-apps/template.html"
              initialTool="get_workout_template"
              onCallTool={handleTool}
            />
          ) : (
            <p className="muted">Select a template to edit it.</p>
          )}
        </div>
        <div className="dash-card" style={{ minWidth: "12rem", alignSelf: "flex-start" }}>
          <h3>Templates</h3>
          {templates === null && <p className="muted">Loading…</p>}
          {templates?.length === 0 && (
            <p className="muted">No templates yet.</p>
          )}
          <ul>
            {templates?.map((t) => (
              <li key={t.id}>
                <button type="button" onClick={() => setSelectedId(t.id)}>
                  {t.name}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
