import { useCallback } from "react";

import { api } from "../api/client";
import { AppRenderer, type ToolResultPayload } from "../mcp-apps/AppRenderer";
import type { components } from "../api/generated";

type NutritionDayOut = components["schemas"]["NutritionDayOut"];
interface Me {
  user_sub: string;
  email: string | null;
  display_name: string | null;
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
  const focus = day.streak_key === null || day.streak_key === "calories"
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
      values: Object.fromEntries(Object.entries(log.values).map(([k, v]) => [k, Number(v)])),
    })),
    summary,
  };
  return {
    content: [{ type: "text", text: JSON.stringify(payload) }],
    structuredContent: payload,
  };
}

export function NutritionPage({ me }: { me: Me }) {
  const handleTool = useCallback(async (name: string): Promise<ToolResultPayload> => {
    if (name !== "get_nutrition_day") throw new Error(`unknown tool: ${name}`);
    const { data, error } = await api.GET("/api/nutrition/day");
    if (error || !data) throw new Error("day fetch failed");
    return toPayload(data);
  }, []);

  return (
    <section>
      <p className="muted">
        Signed in as <strong>{me.display_name ?? me.email ?? me.user_sub}</strong> ✓
      </p>
      <AppRenderer
        bundleUrl="/mcp-apps/nutrition-day.html"
        initialTool="get_nutrition_day"
        onCallTool={handleTool}
        eventsUrl="/api/nutrition/events"
      />
    </section>
  );
}
