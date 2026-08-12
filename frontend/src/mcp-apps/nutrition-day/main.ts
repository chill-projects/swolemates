/**
 * The nutrition-day component. Renders in two hosts from this one bundle:
 *  - Claude, via the `ui://swolemates/nutrition-day.html` MCP resource
 *  - the SPA, via AppRenderer (an iframe + AppBridge backed by the REST API)
 *
 * Any tool call that changes today's totals (`log_nutrition`, `get_nutrition_day`)
 * returns this same payload shape, so the component re-renders fully from whichever
 * result the host pushes — no separate fetch, same pattern as tmpx.
 */

import { App } from "@modelcontextprotocol/ext-apps";

interface TrackableProgress {
  trackable_key: string;
  label: string;
  unit: string;
  consumed: number;
  target: number | null;
}

interface DayLogEntry {
  id: string;
  name: string | null;
  logged_at: string;
  meal_type: string | null;
  values: Record<string, number>;
}

interface NutritionDayPayload {
  date: string;
  hero: TrackableProgress;
  bars: TrackableProgress[];
  streak_key: string | null;
  logs: DayLogEntry[];
  summary: string;
}

const RING_RADIUS = 52;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

const $ = <T extends Element>(id: string): T => {
  const el = document.getElementById(id);
  if (!el) throw new Error(`missing #${id}`);
  return el as unknown as T;
};

const statusEl = $<HTMLParagraphElement>("status");
const ringFillEl = $<SVGCircleElement>("ring-fill");
const ringValueEl = $<HTMLSpanElement>("ring-value");
const ringTargetEl = $<HTMLSpanElement>("ring-target");
const barsEl = $<HTMLDivElement>("bars");
const logsEl = $<HTMLUListElement>("logs");

const app = new App({ name: "Swolemates Nutrition", version: "1.0.0" });

function extractPayload(result: {
  structuredContent?: unknown;
  content?: Array<{ type: string; text?: string }>;
}): NutritionDayPayload | null {
  const structured = result.structuredContent as NutritionDayPayload | undefined;
  if (structured && structured.hero) return structured;
  const text = result.content?.find((c) => c.type === "text")?.text;
  if (!text) return null;
  try {
    const parsed = JSON.parse(text) as NutritionDayPayload;
    return parsed.hero ? parsed : null;
  } catch {
    return null;
  }
}

function renderBar(progress: TrackableProgress): HTMLDivElement {
  const row = document.createElement("div");
  row.className = "bar-row";

  const top = document.createElement("div");
  top.className = "top";
  const label = document.createElement("span");
  label.textContent = progress.label;
  const amount = document.createElement("span");
  amount.className = "amount";
  amount.textContent = progress.target
    ? `${Math.round(progress.consumed)} / ${Math.round(progress.target)}${progress.unit}`
    : `${Math.round(progress.consumed)}${progress.unit}`;
  top.append(label, amount);

  const track = document.createElement("div");
  track.className = "bar-track";
  const fill = document.createElement("div");
  fill.className = "bar-fill";
  const pct = progress.target ? Math.min((progress.consumed / progress.target) * 100, 100) : 0;
  fill.style.width = `${pct}%`;
  track.appendChild(fill);

  row.append(top, track);
  return row;
}

function renderLog(log: DayLogEntry): HTMLLIElement {
  const li = document.createElement("li");

  const name = document.createElement("div");
  name.className = "log-name";
  name.textContent = log.name ?? "Entry";
  if (log.meal_type) {
    const meta = document.createElement("span");
    meta.className = "log-meta";
    meta.textContent = ` · ${log.meal_type}`;
    name.appendChild(meta);
  }

  const values = document.createElement("div");
  values.className = "log-values";
  values.textContent = Object.entries(log.values)
    .map(([key, value]) => `${key}: ${value}`)
    .join(", ");

  li.append(name, values);
  return li;
}

function render(payload: NutritionDayPayload): void {
  statusEl.textContent = payload.summary;

  ringValueEl.textContent = Math.round(payload.hero.consumed).toLocaleString();
  ringTargetEl.textContent = payload.hero.target
    ? `/ ${Math.round(payload.hero.target).toLocaleString()}`
    : "";
  const pct = payload.hero.target
    ? Math.min(payload.hero.consumed / payload.hero.target, 1)
    : 0;
  ringFillEl.style.strokeDasharray = `${RING_CIRCUMFERENCE}`;
  ringFillEl.style.strokeDashoffset = `${RING_CIRCUMFERENCE * (1 - pct)}`;

  barsEl.replaceChildren(...payload.bars.map(renderBar));

  logsEl.replaceChildren(
    ...(payload.logs.length
      ? payload.logs.map(renderLog)
      : [Object.assign(document.createElement("li"), { className: "muted", textContent: "Nothing logged yet." })]),
  );
}

async function callAndRender(name: string, args: Record<string, unknown>): Promise<void> {
  try {
    const result = await app.callServerTool({ name, arguments: args });
    const payload = extractPayload(result);
    if (payload) render(payload);
  } catch (err) {
    statusEl.textContent = "Something went wrong talking to the server.";
    statusEl.className = "error";
    console.error(err);
  }
}

// Hosts with a push channel (the SPA) send fresh results proactively; hosts without
// one (a chat widget) at least get freshness whenever the user returns to the tab.
// No interval polling: in chat hosts every server call may prompt for approval.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") void callAndRender("get_nutrition_day", {});
});

// The host pushes the originating tool's result (e.g. get_nutrition_day) once on render.
app.ontoolresult = (result) => {
  const payload = extractPayload(result);
  if (payload) render(payload);
  else statusEl.textContent = "Waiting for data…";
};

await app.connect();
statusEl.textContent = "Loading…";
