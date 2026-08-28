/**
 * The weekly-pattern + planned-workouts component. Renders in two hosts from this
 * one bundle:
 *  - Claude, via the `ui://swolemates/planned.html` MCP resource
 *  - the SPA, via AppRenderer (an iframe + AppBridge backed by the REST API)
 *
 * Two independent sections: the standing weekly pattern (7 day selects, auto-saves
 * the whole week on any change — `set_weekly_pattern` always replaces the full
 * set) and the next 7 days' planned entries (Start/Skip/Unskip). `start_workout`
 * (called from "Start") returns a *workout-live* payload, not a planned-workouts
 * one — this component doesn't try to render that; it just confirms and refetches
 * its own planned list, on the assumption you're headed to the workout view next.
 */

import { App } from "@modelcontextprotocol/ext-apps";

interface PlannedEntry {
  id: string;
  template_id: string;
  template_name: string;
  scheduled_for: string;
  status: "planned" | "done" | "skipped";
  workout_id: string | null;
  note: string | null;
  exercise_names: string[];
}

interface PatternDay {
  day_of_week: number;
  template_id: string | null;
  template_name: string | null;
}

interface CatalogTemplate {
  id: string;
  name: string;
}

const DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

const $ = <T extends Element>(id: string): T => {
  const el = document.getElementById(id);
  if (!el) throw new Error(`missing #${id}`);
  return el as unknown as T;
};

const statusEl = $<HTMLParagraphElement>("status");
const patternDaysEl = $<HTMLDivElement>("pattern-days");
const patternSectionEl = $<HTMLElement>("pattern-section");
const plannedListEl = $<HTMLUListElement>("planned-list");

let templatesCatalog: CatalogTemplate[] = [];
let currentPattern: PatternDay[] = [];
let currentPlanned: PlannedEntry[] = [];

const app = new App({ name: "Swolemates Planned Workouts", version: "1.0.0" });

function extractPlannedList(result: {
  structuredContent?: unknown;
  content?: Array<{ type: string; text?: string }>;
}): PlannedEntry[] | null {
  const structured = result.structuredContent as { planned?: PlannedEntry[] } | undefined;
  if (structured?.planned) return structured.planned;
  const text = result.content?.find((c) => c.type === "text")?.text;
  if (!text) return null;
  try {
    const parsed = JSON.parse(text) as { planned?: PlannedEntry[] };
    return Array.isArray(parsed.planned) ? parsed.planned : null;
  } catch {
    return null;
  }
}

function extractPattern(result: {
  structuredContent?: unknown;
  content?: Array<{ type: string; text?: string }>;
}): PatternDay[] | null {
  const structured = result.structuredContent as { pattern?: PatternDay[] } | undefined;
  if (structured?.pattern) return structured.pattern;
  const text = result.content?.find((c) => c.type === "text")?.text;
  if (!text) return null;
  try {
    const parsed = JSON.parse(text) as { pattern?: PatternDay[] };
    return Array.isArray(parsed.pattern) ? parsed.pattern : null;
  } catch {
    return null;
  }
}

function formatDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

function renderPatternRow(dayOfWeek: number): HTMLDivElement {
  const row = document.createElement("div");
  row.className = "pattern-row";

  const label = document.createElement("span");
  label.textContent = DAY_LABELS[dayOfWeek] ?? "";

  const select = document.createElement("select");
  select.setAttribute("aria-label", `${DAY_LABELS[dayOfWeek] ?? ""} template`);
  const restOpt = document.createElement("option");
  restOpt.value = "";
  restOpt.textContent = "Rest";
  select.appendChild(restOpt);
  for (const t of templatesCatalog) {
    const opt = document.createElement("option");
    opt.value = t.id;
    opt.textContent = t.name;
    select.appendChild(opt);
  }
  const current = currentPattern.find((d) => d.day_of_week === dayOfWeek);
  select.value = current?.template_id ?? "";
  select.onchange = () => void saveWholePattern();

  row.append(label, select);
  return row;
}

function renderPattern(): void {
  patternDaysEl.replaceChildren(...Array.from({ length: 7 }, (_, i) => renderPatternRow(i)));
}

async function saveWholePattern(): Promise<void> {
  const selects = [...patternDaysEl.querySelectorAll("select")];
  const days = selects.map((sel, i) => ({
    day_of_week: i,
    template_id: sel.value || null,
  }));
  try {
    const result = await app.callServerTool({ name: "set_weekly_pattern", arguments: { days } });
    const pattern = extractPattern(result);
    if (pattern) {
      currentPattern = pattern;
      renderPattern();
      statusEl.textContent = "Pattern saved.";
      statusEl.className = "muted";
    }
  } catch (err) {
    statusEl.textContent = "Something went wrong talking to the server.";
    statusEl.className = "error";
    console.error(err);
  }
}

/** One row of "Next seven days": the date, what's on it, and its one action. */
function renderPlannedEntry(p: PlannedEntry): HTMLLIElement {
  const li = document.createElement("li");
  li.className = `planned-entry planned-entry--${p.status}`;

  const dateEl = document.createElement("span");
  dateEl.className = "planned-date";
  dateEl.textContent = formatDate(p.scheduled_for);

  const main = document.createElement("div");
  main.className = "planned-main";
  const nameEl = document.createElement("strong");
  nameEl.textContent = p.template_name;
  main.appendChild(nameEl);
  if (p.status === "done") {
    const badge = document.createElement("span");
    badge.className = "badge status-done";
    badge.textContent = "done";
    nameEl.insertAdjacentElement("afterend", badge);
  }
  const exercisesEl = document.createElement("div");
  exercisesEl.className = "planned-exercises";
  exercisesEl.textContent =
    p.status === "skipped"
      ? "skipped"
      : p.exercise_names.length > 0
        ? p.exercise_names.join(", ")
        : "";
  main.appendChild(exercisesEl);

  const actions = document.createElement("div");
  actions.className = "planned-actions";
  if (p.status === "planned" && !p.workout_id) {
    const startBtn = document.createElement("button");
    startBtn.type = "button";
    startBtn.className = "btn-primary";
    startBtn.textContent = "Start";
    startBtn.onclick = () => void startFromPlanned(p.id);
    const skipBtn = document.createElement("button");
    skipBtn.type = "button";
    skipBtn.className = "btn-danger";
    skipBtn.textContent = "Skip";
    skipBtn.onclick = () =>
      void callAndRefreshPlanned("update_planned_workout", { planned_id: p.id, action: "skip" });
    actions.append(startBtn, skipBtn);
  } else if (p.status === "skipped") {
    const unskipBtn = document.createElement("button");
    unskipBtn.type = "button";
    unskipBtn.textContent = "Unskip";
    unskipBtn.onclick = () =>
      void callAndRefreshPlanned("update_planned_workout", { planned_id: p.id, action: "unskip" });
    actions.append(unskipBtn);
  }

  li.append(dateEl, main, actions);
  return li;
}

function renderPlanned(): void {
  plannedListEl.replaceChildren(
    ...(currentPlanned.length
      ? currentPlanned.map(renderPlannedEntry)
      : [
          Object.assign(document.createElement("li"), {
            className: "muted",
            textContent: "Nothing scheduled.",
          }),
        ]),
  );
}

async function refreshPlanned(): Promise<void> {
  const result = await app.callServerTool({ name: "get_planned_workouts", arguments: {} });
  const planned = extractPlannedList(result);
  if (planned) {
    currentPlanned = planned;
    renderPlanned();
  }
}

async function callAndRefreshPlanned(name: string, args: Record<string, unknown>): Promise<void> {
  try {
    await app.callServerTool({ name, arguments: args });
    await refreshPlanned();
  } catch (err) {
    statusEl.textContent = "Something went wrong talking to the server.";
    statusEl.className = "error";
    console.error(err);
  }
}

async function startFromPlanned(plannedId: string): Promise<void> {
  try {
    await app.callServerTool({ name: "start_workout", arguments: { planned_id: plannedId } });
    statusEl.textContent = "Workout started — continue in the workout view.";
    statusEl.className = "muted";
    await refreshPlanned();
  } catch (err) {
    statusEl.textContent = "Something went wrong talking to the server.";
    statusEl.className = "error";
    console.error(err);
  }
}

async function loadPatternAndCatalog(): Promise<void> {
  const catalogResult = await app.callServerTool({ name: "list_templates_catalog", arguments: {} });
  const structured = catalogResult.structuredContent as { templates: CatalogTemplate[] } | undefined;
  templatesCatalog = structured?.templates ?? [];

  const patternResult = await app.callServerTool({ name: "get_weekly_pattern", arguments: {} });
  currentPattern = extractPattern(patternResult) ?? [];
  renderPattern();
  if (statusEl.textContent === "Loading…") statusEl.textContent = "";
}

// Hosts with a push channel (the SPA) send fresh results proactively; hosts without
// one (a chat widget) at least get freshness whenever the user returns to the tab.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") void refreshPlanned();
});

// The host pushes the originating tool's result (typically get_planned_workouts)
// once on render; the pattern/catalog are fetched independently below since
// nothing pushes those automatically.
app.ontoolresult = (result) => {
  const planned = extractPlannedList(result);
  if (planned) {
    currentPlanned = planned;
    renderPlanned();
    if (statusEl.textContent === "Loading…" || statusEl.textContent === "Waiting for data…") {
      statusEl.textContent = "";
    }
  } else {
    statusEl.textContent = "Waiting for data…";
  }
};

await app.connect();

// The SPA edits the weekly pattern itself, in the page hero band above this iframe,
// so the pattern section is dropped in that host and kept everywhere else — in a
// chat host this component is the only thing on screen and owns it.
const inSpa = app.getHostVersion()?.name === "swolemates-web";
if (inSpa) patternSectionEl.hidden = true;

statusEl.textContent = "Loading…";
void loadPatternAndCatalog();
