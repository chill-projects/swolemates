import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import { AppRenderer, type ToolResultPayload } from "../mcp-apps/AppRenderer";
import type { components } from "../api/generated";

type NutritionDayOut = components["schemas"]["NutritionDayOut"];
type MealTemplateSummaryOut = components["schemas"]["MealTemplateSummaryOut"];

const numeric = (values: Record<string, string>) =>
  Object.fromEntries(Object.entries(values).map(([k, v]) => [k, Number(v)]));

/** get_nutrition_day defaults to UTC "today" server-side (day.py: "no per-user timezone
 *  yet") — wrong for hours after the user's local midnight and before UTC's (evening,
 *  west of UTC), when it silently shows an empty day instead of what they just logged.
 *  The date alone isn't enough either — the server also needs the UTC offset to bound
 *  "today" at the caller's actual local midnight, not UTC's, or a log made minutes ago
 *  can still fall outside the window (see day.py's tz_offset_minutes). Both come
 *  straight from the browser. */
function todayLocalDate(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function tzOffsetMinutes(): number {
  return new Date().getTimezoneOffset();
}

/** Shape the REST response into the same payload the MCP tools return (numbers
 *  instead of the Decimal-as-string REST wire format), so the component can't tell
 *  which host it's running in. */
function toPayload(day: NutritionDayOut): ToolResultPayload {
  const progress = (p: NutritionDayOut["hero"]) => ({
    trackable_key: p.trackable_key,
    label: p.label,
    unit: p.unit,
    consumed: Number(p.consumed),
    target: p.target === null ? null : Number(p.target),
  });
  const hero = progress(day.hero);
  const bars = day.bars.map(progress);
  const parts = [`${Math.round(hero.consumed).toLocaleString()} ${hero.unit} so far`];
  parts.push(...bars.map((b) => `${Math.round(b.consumed)} ${b.unit} ${b.label.toLowerCase()}`));
  const focus =
    day.streak_key === null || day.streak_key === "calories"
      ? hero
      : bars.find((b) => b.trackable_key === day.streak_key);
  let summary = parts.join(", ");
  if (focus?.target) {
    const remaining = focus.target - focus.consumed;
    summary +=
      remaining >= 0
        ? ` — ${Math.round(remaining).toLocaleString()} ${focus.unit} to go`
        : ` — ${Math.round(-remaining).toLocaleString()} ${focus.unit} over`;
  }

  const payload = {
    date: day.date,
    hero,
    bars,
    streak_key: day.streak_key,
    logs: day.logs.map((log) => ({
      id: log.id,
      name: log.name,
      logged_at: log.logged_at,
      meal_type: log.meal_type,
      values: numeric(log.values),
      items: log.items.map((item) => ({ id: item.id, name: item.name, values: numeric(item.values) })),
    })),
    templates: day.templates.map((template) => ({
      id: template.id,
      name: template.name,
      default_meal_type: template.default_meal_type,
      items: template.items.map((item) => ({
        id: item.id,
        name: item.name,
        serving_description: item.serving_description,
        values: numeric(item.values),
      })),
      totals: numeric(template.totals),
    })),
    summary,
  };
  return {
    content: [{ type: "text", text: JSON.stringify(payload) }],
    structuredContent: payload,
  };
}

export function NutritionPage() {
  // Deleting a meal template is deliberately REST-only, not a chat/MCP tool — the
  // nutrition-day bundle's own comment explains why (it runs unchanged inside Claude,
  // and a delete button there would work in the SPA but silently fail in chat). So
  // this list lives here in plain React, next to the shared iframe rather than inside
  // it. The iframe's own template list stays in sync on its own: delete_meal_template
  // publishes the same "nutrition" SSE event log_nutrition etc. already trigger, which
  // AppRenderer's eventsUrl already re-fetches on.
  const [templates, setTemplates] = useState<MealTemplateSummaryOut[] | null>(null);

  const refreshTemplates = useCallback(async () => {
    const { data } = await api.GET("/api/nutrition/templates");
    setTemplates(data ?? []);
  }, []);

  useEffect(() => {
    void refreshTemplates();
  }, [refreshTemplates]);

  const handleDeleteTemplate = useCallback(
    async (templateId: string) => {
      const { error } = await api.DELETE("/api/nutrition/templates/{template_id}", {
        params: { path: { template_id: templateId } },
      });
      if (!error) void refreshTemplates();
    },
    [refreshTemplates],
  );

  const handleTool = useCallback(
    async (name: string, args: Record<string, unknown>): Promise<ToolResultPayload> => {
      switch (name) {
        case "get_nutrition_day":
          break;
        // Pre-existing gap: nothing in the SPA ever called this until the food-search
        // "Log" button (meal templates go through log_meal_template instead), so it
        // fell to the `default: throw` below, unnoticed, until now.
        case "log_nutrition": {
          const { error } = await api.POST("/api/nutrition/logs", {
            body: {
              entries: (args.entries as { trackable_key: string; value: number }[]) ?? [],
              name: (args.name as string | undefined) ?? null,
              meal_type: (args.meal_type as string | undefined) ?? null,
              source: "manual",
            },
          });
          if (error) throw new Error("log food failed");
          break;
        }
        case "search_food_facts": {
          const { data, error } = await api.GET("/api/food-facts/search", {
            params: {
              query: {
                query: args.query as string | undefined,
                barcode: args.barcode as string | undefined,
              },
            },
          });
          if (error) throw new Error("food search failed");
          const payload = { matches: data ?? [] };
          return { content: [{ type: "text", text: JSON.stringify(payload) }], structuredContent: payload };
        }
        case "save_meal_template": {
          const { error } = await api.POST("/api/nutrition/templates", {
            body: {
              name: String(args.name ?? ""),
              log_ids: (args.log_ids as string[]) ?? [],
            },
          });
          if (error) throw new Error("save template failed");
          void refreshTemplates();
          break;
        }
        case "log_meal_template": {
          const templateId = String(args.template_id ?? "");
          const { error } = await api.POST("/api/nutrition/templates/{template_id}/log", {
            params: { path: { template_id: templateId } },
            body: { multiplier: 1 },
          });
          if (error) throw new Error("log template failed");
          break;
        }
        case "update_meal_template_item": {
          const { error } = await api.PATCH("/api/nutrition/templates/{template_id}/items/{item_id}", {
            params: {
              path: {
                template_id: String(args.template_id ?? ""),
                item_id: String(args.item_id ?? ""),
              },
            },
            body: {
              name: String(args.name ?? ""),
              serving_description: (args.serving_description as string | null) ?? null,
              values: (args.values as Record<string, number>) ?? {},
            },
          });
          if (error) throw new Error("update template item failed");
          break;
        }
        default:
          throw new Error(`unknown tool: ${name}`);
      }
      const { data, error } = await api.GET("/api/nutrition/day", {
        params: { query: { day: todayLocalDate(), tz_offset_minutes: tzOffsetMinutes() } },
      });
      if (error || !data) throw new Error("day fetch failed");
      return toPayload(data);
    },
    [refreshTemplates],
  );

  return (
    <section>
      <h2>Nutrition</h2>
      <AppRenderer
        bundleUrl="/mcp-apps/nutrition-day.html"
        initialTool="get_nutrition_day"
        onCallTool={handleTool}
        eventsUrl="/api/nutrition/events"
      />
      {templates != null && templates.length > 0 && (
        <div className="dash-card">
          <div className="dash-card-header">
            <span className="dash-card-title">Manage meal templates</span>
          </div>
          <ul>
            {templates.map((t) => (
              <li key={t.id} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <span style={{ flex: 1 }}>
                  {t.name}{" "}
                  <span className="muted">
                    ({t.items.length} item{t.items.length === 1 ? "" : "s"})
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => void handleDeleteTemplate(t.id)}
                  aria-label={`Delete ${t.name}`}
                  title="Delete template"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
