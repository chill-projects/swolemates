import { useCallback } from "react";

import { api } from "../api/client";
import { AppRenderer, type ToolResultPayload } from "../mcp-apps/AppRenderer";

interface Me {
  user_sub: string;
  email: string | null;
  display_name: string | null;
}

function toPayload(key: string, data: unknown): ToolResultPayload {
  const payload = { [key]: data };
  return { content: [{ type: "text", text: JSON.stringify(payload) }], structuredContent: payload };
}

export function PlannedPage({ me }: { me: Me }) {
  const handleTool = useCallback(
    async (name: string, args: Record<string, unknown>): Promise<ToolResultPayload> => {
      switch (name) {
        case "list_templates_catalog": {
          const { data, error } = await api.GET("/api/templates");
          if (error || !data) throw new Error("templates fetch failed");
          return toPayload(
            "templates",
            data.map((t) => ({ id: t.id, name: t.name })),
          );
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
        default:
          throw new Error(`unknown tool: ${name}`);
      }
    },
    [],
  );

  return (
    <section>
      <h2>Planned</h2>
      <p className="muted">
        Signed in as <strong>{me.display_name ?? me.email ?? me.user_sub}</strong> ✓
      </p>
      <AppRenderer
        bundleUrl="/mcp-apps/planned.html"
        initialTool="get_planned_workouts"
        onCallTool={handleTool}
        eventsUrl="/api/workouts/events"
      />
    </section>
  );
}
