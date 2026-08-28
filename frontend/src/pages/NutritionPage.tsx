import { useCallback, useState } from "react";

import { api } from "../api/client";
import { PageHero, Ring } from "../components/ui";
import { AppRenderer, type ToolResultPayload } from "../mcp-apps/AppRenderer";
import type { components } from "../api/generated";
import { dateFromIso } from "../lib/datetime";

type NutritionDayOut = components["schemas"]["NutritionDayOut"];

const numeric = (values: Record<string, string>) =>
  Object.fromEntries(Object.entries(values).map(([k, v]) => [k, Number(v)]));

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

/** The subset of the day payload the hero band reads. Same object the component
 *  inside the iframe is rendering — see AppRenderer's `onResult`. */
type DayState = {
  date: string;
  hero: { unit: string; consumed: number; target: number | null };
  bars: { trackable_key: string; unit: string; consumed: number; target: number | null }[];
  logs: unknown[];
};

function isDayState(value: unknown): value is DayState {
  return typeof value === "object" && value !== null && "hero" in value && "logs" in value;
}

const shortfall = (p: { consumed: number; target: number | null }) =>
  p.target === null ? null : p.target - p.consumed;

/** "23 g of protein short, 460 kcal to spend." — whichever of the two still has
 *  room, in that order, since protein is the one people actually miss. */
function directive(day: DayState | null): string {
  if (!day) return "Today’s food, as it lands.";
  const protein = day.bars.find((b) => b.trackable_key === "protein_g");
  const proteinLeft = protein ? shortfall(protein) : null;
  const kcalLeft = shortfall(day.hero);
  const parts: string[] = [];
  if (proteinLeft !== null && proteinLeft > 0) {
    parts.push(`${Math.round(proteinLeft)} ${protein!.unit} of protein short`);
  }
  if (kcalLeft !== null && kcalLeft > 0) {
    parts.push(`${Math.round(kcalLeft).toLocaleString()} ${day.hero.unit} to spend`);
  }
  return parts.length > 0 ? `${parts.join(", ")}.` : "Every target met for today.";
}

const MACRO_COLORS: Record<string, string> = {
  protein_g: "var(--teal)",
  carbs_g: "var(--gold)",
  fat_g: "var(--plum)",
  fiber_g: "var(--coral)",
};

/** The calorie dial and the macro bars, in the band — the shape 3a opens with. The
 *  component below reads the same payload and drops its own copy of this block when
 *  it detects the SPA as its host, so the day is only drawn once. */
function DayRings({ day }: { day: DayState }) {
  const pct = (p: { consumed: number; target: number | null }) =>
    p.target === null || p.target <= 0 ? 0 : p.consumed / p.target;
  return (
    <div className="hero-rings hero-rings--macros">
      <Ring
        label="Calories"
        value={Math.round(day.hero.consumed).toLocaleString()}
        sub={day.hero.target === null ? day.hero.unit : `of ${Math.round(day.hero.target).toLocaleString()}`}
        fraction={pct(day.hero)}
        color="var(--teal)"
      />
      <div className="macro-bars">
        {day.bars.map((bar) => (
          <div key={bar.trackable_key}>
            <div className="macro-bar-label">
              <span>{macroLabel(bar.trackable_key)}</span>
              <span>
                {Math.round(bar.consumed)}
                {bar.target === null ? "" : ` / ${Math.round(bar.target)}`} {bar.unit}
              </span>
            </div>
            <div className="macro-bar-track">
              <div
                className="macro-bar-fill"
                style={{
                  width: `${Math.min(pct(bar) * 100, 100)}%`,
                  background: MACRO_COLORS[bar.trackable_key] ?? "var(--ink-soft)",
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function macroLabel(key: string): string {
  return key.replace(/_g$/, "").replace(/^./, (c) => c.toUpperCase());
}

export function NutritionPage() {
  const [day, setDay] = useState<DayState | null>(null);
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
          break;
        }
        case "delete_meal_template": {
          const { error } = await api.DELETE("/api/nutrition/templates/{template_id}", {
            params: { path: { template_id: String(args.template_id ?? "") } },
          });
          if (error) throw new Error("delete template failed");
          break;
        }
        case "delete_nutrition_log": {
          const { error } = await api.DELETE("/api/nutrition/logs/{log_id}", {
            params: { path: { log_id: String(args.log_id ?? "") } },
          });
          if (error) throw new Error("delete log failed");
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
      // No `day` param: the server resolves "today" in the caller's zone from the
      // `X-Timezone` header (see api/client.ts).
      const { data, error } = await api.GET("/api/nutrition/day", {});
      if (error || !data) throw new Error("day fetch failed");
      return toPayload(data);
    },
    [],
  );

  const entries = day?.logs.length ?? 0;
  const dayLabel = day
    ? dateFromIso(day.date).toLocaleDateString(undefined, {
        weekday: "long",
        day: "numeric",
        month: "long",
      })
    : "Today";

  return (
    <>
      <PageHero
        eyebrow={`${dayLabel} · ${entries} ${entries === 1 ? "entry" : "entries"} logged`}
        title={directive(day)}
        aside={day ? <DayRings day={day} /> : undefined}
      />
      <div className="page-body">
        <AppRenderer
          bundleUrl="/mcp-apps/nutrition-day.html"
          initialTool="get_nutrition_day"
          onCallTool={handleTool}
          // Ignore anything that isn't a day payload — food search comes back
          // through here too, and it must not blank the header.
          onResult={(result) => {
            if (isDayState(result.structuredContent)) setDay(result.structuredContent);
          }}
          eventsUrl="/api/nutrition/events"
        />
      </div>
    </>
  );
}
